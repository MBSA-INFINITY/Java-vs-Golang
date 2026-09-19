// go-compute is a CPU-bound benchmark service.
//
// It exposes a /compute endpoint that performs naive trial-division prime
// counting over a configurable range, optionally fanned out across multiple
// goroutines. The goal is purely to burn CPU cycles in a way that is
// identical (algorithmically) to the Java counterpart, so that raw
// throughput/latency/concurrency-scaling can be compared fairly.
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"runtime"
	"strconv"
	"sync"
	"sync/atomic"
	"time"
)

var (
	totalRequests   int64
	totalDurationNs int64
	peakGoroutines  int64
)

func queryInt(r *http.Request, name string, def int) int {
	if v := r.URL.Query().Get(name); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			return n
		}
	}
	return def
}

// isPrime is a deliberately naive O(sqrt(n)) trial-division test - CPU heavy by design.
func isPrime(n int) bool {
	if n < 2 {
		return false
	}
	for i := 2; i*i <= n; i++ {
		if n%i == 0 {
			return false
		}
	}
	return true
}

func countPrimesInRange(lo, hi int) int {
	count := 0
	for i := lo; i < hi; i++ {
		if isPrime(i) {
			count++
		}
	}
	return count
}

func recordPeakGoroutines() {
	if g := int64(runtime.NumGoroutine()); g > atomic.LoadInt64(&peakGoroutines) {
		atomic.StoreInt64(&peakGoroutines, g)
	}
}

func computeHandler(w http.ResponseWriter, r *http.Request) {
	start := time.Now()

	limit := queryInt(r, "limit", 200000)
	workers := queryInt(r, "workers", 1)
	if workers > 4096 {
		workers = 4096
	}
	if workers > limit {
		workers = limit
	}

	chunk := limit / workers
	var wg sync.WaitGroup
	counts := make([]int, workers)

	for w := 0; w < workers; w++ {
		lo := w * chunk
		hi := lo + chunk
		if w == workers-1 {
			hi = limit
		}
		wg.Add(1)
		go func(idx, lo, hi int) {
			defer wg.Done()
			counts[idx] = countPrimesInRange(lo, hi)
		}(w, lo, hi)
	}
	wg.Wait()

	total := 0
	for _, c := range counts {
		total += c
	}

	elapsed := time.Since(start)
	atomic.AddInt64(&totalRequests, 1)
	atomic.AddInt64(&totalDurationNs, elapsed.Nanoseconds())
	recordPeakGoroutines()

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"workload":   "compute",
		"limit":      limit,
		"workers":    workers,
		"primeCount": total,
		"durationMs": float64(elapsed.Microseconds()) / 1000.0,
		"goroutines": runtime.NumGoroutine(),
	})
}

func metricsHandler(w http.ResponseWriter, r *http.Request) {
	var m runtime.MemStats
	runtime.ReadMemStats(&m)
	reqs := atomic.LoadInt64(&totalRequests)
	durNs := atomic.LoadInt64(&totalDurationNs)
	avgMs := 0.0
	if reqs > 0 {
		avgMs = float64(durNs) / float64(reqs) / 1e6
	}

	w.Header().Set("Content-Type", "text/plain; version=0.0.4")
	fmt.Fprintf(w, "# HELP app_requests_total Total number of processed requests\n# TYPE app_requests_total counter\napp_requests_total %d\n", reqs)
	fmt.Fprintf(w, "# HELP app_request_avg_duration_ms Average request duration in ms\n# TYPE app_request_avg_duration_ms gauge\napp_request_avg_duration_ms %f\n", avgMs)
	fmt.Fprintf(w, "# HELP app_goroutines Current number of goroutines\n# TYPE app_goroutines gauge\napp_goroutines %d\n", runtime.NumGoroutine())
	fmt.Fprintf(w, "# HELP app_peak_goroutines Peak observed goroutines\n# TYPE app_peak_goroutines gauge\napp_peak_goroutines %d\n", atomic.LoadInt64(&peakGoroutines))
	fmt.Fprintf(w, "# HELP app_heap_alloc_bytes Heap memory currently allocated\n# TYPE app_heap_alloc_bytes gauge\napp_heap_alloc_bytes %d\n", m.HeapAlloc)
	fmt.Fprintf(w, "# HELP app_num_gc Number of completed GC cycles\n# TYPE app_num_gc counter\napp_num_gc %d\n", m.NumGC)
	fmt.Fprintf(w, "# HELP app_num_cpu Logical CPUs visible to the process\n# TYPE app_num_cpu gauge\napp_num_cpu %d\n", runtime.NumCPU())
	fmt.Fprintf(w, "# HELP app_gomaxprocs Current GOMAXPROCS setting\n# TYPE app_gomaxprocs gauge\napp_gomaxprocs %d\n", runtime.GOMAXPROCS(0))
}

func statsLogger() {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()
	for range ticker.C {
		var m runtime.MemStats
		runtime.ReadMemStats(&m)
		log.Printf("[stats] goroutines=%d peakGoroutines=%d heapAllocMB=%.2f numGC=%d totalRequests=%d gomaxprocs=%d",
			runtime.NumGoroutine(), atomic.LoadInt64(&peakGoroutines), float64(m.HeapAlloc)/1024/1024,
			m.NumGC, atomic.LoadInt64(&totalRequests), runtime.GOMAXPROCS(0))
	}
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	go statsLogger()

	mux := http.NewServeMux()
	mux.HandleFunc("/compute", computeHandler)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	mux.HandleFunc("/metrics", metricsHandler)

	log.Printf("go-compute listening on :%s (GOMAXPROCS=%d, NumCPU=%d)", port, runtime.GOMAXPROCS(0), runtime.NumCPU())
	log.Fatal(http.ListenAndServe(":"+port, mux))
}
