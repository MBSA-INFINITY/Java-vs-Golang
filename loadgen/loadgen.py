"""
Step-load concurrency ramp tester.

Hits a single target URL (a compute or io endpoint on one of the four
benchmark services) at increasing levels of concurrency, and reports
throughput / latency percentiles / error-rate at each level so you can
visually pinpoint the exact concurrency level where a given
language+workload combination starts to degrade.

All configuration is via environment variables (see README.md at the
repo root for the full list and k8s Job examples).
"""
import asyncio
import csv
import os
import statistics
import time
from datetime import datetime, timezone

import aiohttp

TARGET_URL = os.environ["TARGET_URL"]
CONCURRENCY_LEVELS = [int(x) for x in os.environ.get(
    "CONCURRENCY_LEVELS", "1,10,50,100,250,500,1000,2000"
).split(",") if x.strip()]
DURATION_SEC = int(os.environ.get("DURATION_SEC", "20"))
REQUEST_TIMEOUT_SEC = int(os.environ.get("REQUEST_TIMEOUT_SEC", "10"))
MAX_ERROR_RATE = float(os.environ.get("MAX_ERROR_RATE", "0.05"))
P99_DEGRADATION_MULTIPLIER = float(os.environ.get("P99_DEGRADATION_MULTIPLIER", "5"))
STOP_ON_DEGRADATION = os.environ.get("STOP_ON_DEGRADATION", "false").lower() == "true"
OUTPUT_CSV = os.environ.get("OUTPUT_CSV", "/tmp/results.csv")
LABEL = os.environ.get("LABEL", "run")


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat()} [loadgen:{LABEL}] {msg}", flush=True)


async def worker(session: aiohttp.ClientSession, stop_time: float, latencies: list, counters: dict) -> None:
    while time.monotonic() < stop_time:
        start = time.monotonic()
        try:
            async with session.get(TARGET_URL) as resp:
                await resp.read()
                elapsed = time.monotonic() - start
                latencies.append(elapsed)
                if resp.status >= 400:
                    counters["errors"] += 1
                else:
                    counters["success"] += 1
        except Exception:
            latencies.append(time.monotonic() - start)
            counters["errors"] += 1


async def run_level(concurrency: int) -> dict:
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SEC)
    connector = aiohttp.TCPConnector(limit=0)
    latencies: list = []
    counters = {"success": 0, "errors": 0}

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        stop_time = time.monotonic() + DURATION_SEC
        tasks = [asyncio.create_task(worker(session, stop_time, latencies, counters)) for _ in range(concurrency)]
        await asyncio.gather(*tasks)

    total = counters["success"] + counters["errors"]
    rps = total / DURATION_SEC if DURATION_SEC > 0 else 0.0
    error_rate = counters["errors"] / total if total > 0 else 0.0

    if latencies:
        s = sorted(latencies)
        p50 = s[int(len(s) * 0.50)] * 1000
        p90 = s[min(int(len(s) * 0.90), len(s) - 1)] * 1000
        p99 = s[min(int(len(s) * 0.99), len(s) - 1)] * 1000
        avg = statistics.mean(latencies) * 1000
    else:
        p50 = p90 = p99 = avg = 0.0

    return {
        "concurrency": concurrency,
        "total_requests": total,
        "success": counters["success"],
        "errors": counters["errors"],
        "error_rate": error_rate,
        "rps": rps,
        "avg_ms": avg,
        "p50_ms": p50,
        "p90_ms": p90,
        "p99_ms": p99,
    }


async def main() -> None:
    log(f"target={TARGET_URL} levels={CONCURRENCY_LEVELS} duration_per_level={DURATION_SEC}s")
    results = []
    baseline_p99 = None

    with open(OUTPUT_CSV, "w", newline="") as f:
        fieldnames = ["concurrency", "total_requests", "success", "errors",
                      "error_rate", "rps", "avg_ms", "p50_ms", "p90_ms", "p99_ms"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for level in CONCURRENCY_LEVELS:
            log(f"--- testing concurrency={level} for {DURATION_SEC}s ---")
            result = await run_level(level)
            results.append(result)
            writer.writerow(result)
            f.flush()

            if baseline_p99 is None and result["p99_ms"] > 0:
                baseline_p99 = result["p99_ms"]

            degraded = (result["error_rate"] > MAX_ERROR_RATE) or (
                baseline_p99 is not None and result["p99_ms"] > baseline_p99 * P99_DEGRADATION_MULTIPLIER
            )

            log(
                f"RESULT concurrency={level} rps={result['rps']:.2f} "
                f"avg_ms={result['avg_ms']:.2f} p50_ms={result['p50_ms']:.2f} "
                f"p90_ms={result['p90_ms']:.2f} p99_ms={result['p99_ms']:.2f} "
                f"errors={result['errors']} error_rate={result['error_rate']:.2%}"
            )

            if degraded:
                log(
                    f"*** DEGRADATION DETECTED at concurrency={level} "
                    f"(error_rate={result['error_rate']:.2%}, p99={result['p99_ms']:.2f}ms "
                    f"vs baseline={baseline_p99:.2f}ms) ***"
                )
                if STOP_ON_DEGRADATION:
                    log("STOP_ON_DEGRADATION=true, halting ramp test.")
                    break

    log("=== summary ===")
    for r in results:
        log(
            f"concurrency={r['concurrency']:>6} rps={r['rps']:>9.2f} "
            f"p50={r['p50_ms']:>8.2f}ms p90={r['p90_ms']:>8.2f}ms p99={r['p99_ms']:>8.2f}ms "
            f"errors={r['errors']:>6} error_rate={r['error_rate']:.2%}"
        )
    log(f"results written to {OUTPUT_CSV}")


if __name__ == "__main__":
    asyncio.run(main())
