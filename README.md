# Java (Spring Boot + Virtual Threads) vs Go (goroutines) — Performance Deep Dive

A self-contained benchmark stack to compare **Go (goroutines)** against **Java 21
(virtual threads, Spring Boot 3.3)** under identical CPU/memory constraints, across
three workload shapes:

1. **Compute-bound** — CPU-saturating work (prime counting via trial division).
2. **Network-bound / IO-bound** — requests that block on a slow downstream call.
3. **Disk-bound / storage-IO** — requests that write JSON payloads to disk,
   `fsync` them, read them back, and decode them to exercise real disk flush and
   file I/O cost.

The goal isn't a synthetic "hello world" benchmark — it's to find the **concurrency
level where each language/runtime starts to degrade** (rising p99 latency, rising
error rate, dropping RPS) under the *same* CPU and memory limits.

Everything is designed to be built and run **only inside Kubernetes** — nothing here
needs to run locally beyond `docker build`.

---

## 1. Repository layout

```
golang/
  go-compute/       # CPU-bound Go service   (net/http + goroutines, stdlib only)
  go-network/       # IO-bound Go service    (net/http + goroutines, stdlib only)
  go-diskio/        # Disk-IO Go service     (write+fsync+read+decode JSON files)
java/
  java-compute/     # CPU-bound Spring Boot service (Java 21 virtual threads)
  java-network/     # IO-bound Spring Boot service  (Java 21 virtual threads)
  java-diskio/      # Disk-IO Spring Boot service   (write+fsync+read+decode JSON files)
loadgen/            # Python asyncio load generator (step-concurrency ramp tester)
manifest.yaml        # Namespace + Deployments + Services + (suspended) load-test Jobs
```

Each service folder is fully independent (own `go.mod` / `pom.xml` / `Dockerfile`) so
they can be built and pushed as separate container images.

---

## 2. Workload design

### 2.1 Compute-bound: `GET /compute?limit=200000&workers=1`

Both languages run the **identical algorithm**: naive O(√n) trial-division
primality testing, counting all primes in `[0, limit)`. This is pure CPU work with
no I/O, allocation-light, and easy to scale up/down via `limit`.

- `limit` — how much work one request does (raise this to increase per-request CPU cost).
- `workers` — fan the range out across N goroutines / N virtual threads *within a
  single request* (default 1). Concurrency across *requests* is what the load
  generator controls — that's the real axis you're measuring.

Response includes `durationMs`, `primeCount`, and current in-flight/goroutine counts.

### 2.2 Network-bound: `GET /io?delayMs=50&calls=1`

Each request triggers `calls` concurrent outbound HTTP calls (goroutines / virtual
threads) to a `/delay?ms=<delayMs>` endpoint (defaults to itself, override with the
`DOWNSTREAM_URL` env var) which just sleeps for `delayMs` — simulating a slow
DB/remote API. This is a **real socket round trip**, not just a timer, so it
exercises the HTTP client, connection handling, and the language's concurrency
model exactly the way a real backend-for-backend call would.

This is exactly the scenario where:
- **Go**: goroutines are ~2KB stacks, park cheaply on network waits, scale to huge
  numbers of in-flight requests with a tiny memory footprint.
- **Java 21**: virtual threads are designed to solve the same problem — unmount
  from the OS/carrier thread while blocked, so `spring.threads.virtual.enabled=true`
  lets Tomcat handle thousands of concurrent blocking requests without exhausting
  platform threads.

### 2.3 Disk-bound: `GET /diskio?records=1000&workers=1`

Each request creates `workers` independent JSON payloads, writes them to a fresh file,
`fsync`s them to force a real flush past the page cache, reads them back, and
unmarshals the data. This is a **real storage-IO workload**, not just a timer or
in-memory conversion, so it exercises the filesystem, JVM/Go runtime file APIs, and
blocking disk semantics under concurrency.

This makes the disk benchmark a clean comparison point for:
- **Go**: many goroutines doing sync file writes/reads in parallel under the same
  process budget.
- **Java 21**: many virtual threads each doing their own write+fsync+read cycle and
  sharing the same 1 CPU / 1 GiB pod limit.

### 2.4 Why not a synthetic sleep for compute or matrix math for IO?

Keeping the workload types cleanly separated (pure CPU vs pure IO-wait vs real disk
flushes) makes it obvious *why* one runtime wins in one case and not the other,
instead of muddying the comparison with mixed workloads.

---

## 3. Observability built into every service

Every service exposes:

| Endpoint | Purpose |
|---|---|
| `/healthz` (Go & Java) | liveness/readiness probe |
| `/metrics` (Go, Prometheus text format) | `app_requests_total`, `app_goroutines`, `app_peak_goroutines`, `app_heap_alloc_bytes`, `app_gomaxprocs`, `app_inflight_requests` (network only), `app_errors_total` (network only) |
| `/actuator/prometheus` (Java, via Micrometer) | JVM memory/GC/thread metrics **plus** the same custom `app_requests_total` / `app_inflight_requests` / `app_errors_total` gauges for parity with Go |

**Every service also logs a stats line every 5 seconds to stdout** — so `kubectl logs`
alone gives you a live, human-readable trace of concurrency and memory over time:

```
# Go
[stats] goroutines=812 peakGoroutines=1024 heapAllocMB=42.10 numGC=6 totalRequests=15234 gomaxprocs=1

# Java
[stats] inFlight=498 platformThreads=24 peakPlatformThreads=26 heapUsedMB=310 totalRequests=15012 availableProcessors=1
```

Note the contrast: Go's `goroutines` count scales roughly 1:1 with concurrent
requests-in-flight, while Java's `platformThreads` stays flat/low (virtual threads
aren't OS threads) — that's the core architectural difference you're benchmarking.

Both `prometheus.io/scrape` annotations are already set in `manifest.yaml`, so
Hydra/Prometheus should auto-discover all four services.

---

## 4. Build the images

Replace `<REGISTRY>` with your actual registry/repo prefix (Docker Hub, ACR, GHCR, etc).

```powershell
$REGISTRY = "<REGISTRY>"

docker build -t $REGISTRY/go-compute:latest    ./golang/go-compute
docker build -t $REGISTRY/go-network:latest    ./golang/go-network
docker build -t $REGISTRY/go-diskio:latest     ./golang/go-diskio
docker build -t $REGISTRY/java-compute:latest  ./java/java-compute
docker build -t $REGISTRY/java-network:latest  ./java/java-network
docker build -t $REGISTRY/java-diskio:latest   ./java/java-diskio
docker build -t $REGISTRY/loadgen:latest       ./loadgen
```

Push all seven:

```powershell
docker push $REGISTRY/go-compute:latest
docker push $REGISTRY/go-network:latest
docker push $REGISTRY/go-diskio:latest
docker push $REGISTRY/java-compute:latest
docker push $REGISTRY/java-network:latest
docker push $REGISTRY/java-diskio:latest
docker push $REGISTRY/loadgen:latest
```

Then edit `manifest.yaml` and replace every `<REGISTRY>` placeholder (8 occurrences:
4 service Deployments + 4 loadgen Jobs) to match your registry.

```powershell
(Get-Content manifest.yaml) -replace '<REGISTRY>', $REGISTRY | Set-Content manifest.yaml
```

---

## 5. Deploy to Kubernetes

```powershell
kubectl apply -f manifest.yaml
kubectl -n bench get pods -w
```

This creates:
- Namespace `bench`
- 6 always-on Deployments + ClusterIP Services for the three workload families:
  `go-compute`, `go-network`, `go-diskio`, `java-compute`, `java-network`,
  `java-diskio` — each pinned to **1 CPU / 1Gi memory limit** (500m/512Mi
  requests) so the comparison is apples-to-apples.
- 6 **suspended** Jobs (`loadgen-go-compute`, `loadgen-go-network`,
  `loadgen-go-diskio`, `loadgen-java-compute`, `loadgen-java-network`,
  `loadgen-java-diskio`) that won't run until you resume them.

> Resource sizing: `GOMAXPROCS=1` is set explicitly for the Go pods (the Go runtime
> reads this env var natively at startup). Java relies on `-XX:+UseContainerSupport`
> (default since JDK 10) to detect the cgroup CPU limit automatically and size its
> thread pools/heap accordingly — no extra flags needed beyond `-XX:MaxRAMPercentage`.

---

## 6. Running a load test

Only run **one** Job at a time so pods aren't competing for the same node's spare
CPU. Resume a suspended Job with:

```powershell
kubectl -n bench patch job loadgen-go-compute -p '{\"spec\":{\"suspend\":false}}'
kubectl -n bench logs -f job/loadgen-go-compute
```

When it finishes, delete it before re-running (Job pod specs are immutable):

```powershell
kubectl -n bench delete job loadgen-go-compute
kubectl apply -f manifest.yaml   # recreates it (suspended) for next time
kubectl -n bench patch job loadgen-go-compute -p '{\"spec\":{\"suspend\":false}}'
```

Repeat for `loadgen-go-network`, `loadgen-go-diskio`, `loadgen-java-compute`,
`loadgen-java-network`, and `loadgen-java-diskio`.

### Tuning a run

Edit the Job's `env` block (or `kubectl -n bench set env job/... KEY=VALUE` before
resuming) to change:

| Env var | Meaning |
|---|---|
| `TARGET_URL` | full URL incl. query params hit on every request |
| `CONCURRENCY_LEVELS` | comma list, e.g. `1,10,50,100,250,500,1000,2000,5000` |
| `DURATION_SEC` | seconds spent at each concurrency level |
| `MAX_ERROR_RATE` | error-rate threshold (default 0.05) that flags degradation |
| `P99_DEGRADATION_MULTIPLIER` | flags degradation once p99 > baseline_p99 × this (default 5) |
| `STOP_ON_DEGRADATION` | `"true"` to stop the ramp as soon as degradation is flagged |

To push compute harder, bump `limit` (e.g. `limit=1000000`) or `workers` in
`TARGET_URL`. To push IO harder, bump `delayMs` or `calls`.

---

## 7. Reading the results

### 7.1 From the load generator logs

Each concurrency level prints one clear `RESULT` line:

```
RESULT concurrency=500 rps=812.44 avg_ms=612.10 p50_ms=580.20 p90_ms=910.44 p99_ms=1500.83 errors=12 error_rate=1.20%
*** DEGRADATION DETECTED at concurrency=1000 (error_rate=8.40%, p99=4210.55ms vs baseline=95.10ms) ***
```

Scan top-to-bottom for the first `DEGRADATION DETECTED` line — that concurrency
level is where that language+workload combo starts to fall over under the pod's
resource limits. A CSV (`/tmp/results.csv` inside the loadgen pod) has the same data
if you want to `kubectl cp` it out for charting.

### 7.2 From the service logs

```powershell
kubectl -n bench logs -f deploy/go-compute
kubectl -n bench logs -f deploy/go-diskio
kubectl -n bench logs -f deploy/java-compute
kubectl -n bench logs -f deploy/java-diskio
```

Watch `goroutines`/`inFlight` climb with concurrency, and `heapAllocMB`/`heapUsedMB`
for memory pressure. Java's `platformThreads` staying flat while `inFlight` climbs
into the hundreds/thousands is the virtual-thread story playing out live. The disk
workloads add a second kind of blocking behavior: each request writes and reads files,
so you can compare how the runtime handles real storage I/O under the same pod limits.

### 7.3 From Prometheus/Hydra

Scrape targets are already annotated. Useful queries once wired up:
- `app_goroutines` / `app_inflight_requests` vs time, per pod
- `app_peak_goroutines` (Go) vs `jvm_threads_live_threads` (Java, built-in Micrometer metric)
- `process_cpu_usage` / `system_cpu_usage` (Java, built-in) vs `kubectl top pod` for Go
- `jvm_gc_pause_seconds` (Java) — GC pauses are a real cost Go doesn't pay the same way

### 7.4 Parameters to compare, side by side

| Parameter | Where to find it |
|---|---|
| RPS at each concurrency level | loadgen `RESULT` lines |
| p50/p90/p99 latency | loadgen `RESULT` lines |
| Error rate | loadgen `RESULT` lines |
| Concurrency level at first degradation | first `DEGRADATION DETECTED` line |
| Goroutine / in-flight-request count | service stdout `[stats]` lines, or `/metrics` |
| Memory usage under load | `heapAllocMB` (Go) / `heapUsedMB` (Java), or `kubectl top pod` |
| CPU usage under load | `kubectl top pod`, or Micrometer `process_cpu_usage` (Java) |
| Cold-start / warm-up effect | compare the first vs later concurrency levels — JIT warm-up shows up as Java improving over the first 1-2 levels while Go is flat from the start |
| GC pauses (Java only) | `jvm_gc_pause_seconds` via `/actuator/prometheus` |

---

## 8. Expected shape of the conclusion (fill in with your actual numbers)

- **Compute-bound**: both are pinned to the same `GOMAXPROCS`/`availableProcessors`,
  so throughput should scale similarly with CPU once JIT warm-up settles for Java;
  Go has no warm-up penalty and a smaller baseline memory footprint.
- **Network-bound**: this is where virtual threads vs goroutines is decided.
  Watch which one sustains a higher concurrency level before p99/error-rate blow up
  under the **same 1Gi memory limit** — that's your practical answer to "how many
  concurrent blocking-IO requests can this pod handle before I need to scale out?"
- **Disk-bound**: compare write+fsync+read throughput and latency under pressure.
  This workload is particularly good for seeing how each runtime handles a burst of
  real storage operations before the pod starts to saturate or fail requests.

Use the numbers you collect from section 7 to write your own conclusion — the
framework above is designed to make that a matter of reading logs, not guessing.

---

## 9. Cleanup

```powershell
kubectl delete namespace bench
```
