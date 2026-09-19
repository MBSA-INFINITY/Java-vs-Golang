// go-network is an IO-bound (network) benchmark service.
//
// /io fans out `calls` concurrent outbound HTTP requests (goroutines) to a
// downstream endpoint (by default itself) which sleeps for `delayMs` to
// simulate a slow dependency (DB call, remote API, etc). This exercises the
// exact thing goroutines are good at: parking cheaply while waiting on
// network IO so a huge number of concurrent requests can be in flight at
// once with a tiny memory footprint.
package main

import (
	"encoding/json"
	"fmt"
	"io"
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
	totalRequests    int64
	totalDurationNs  int64
	peakGoroutines   int64
	inFlightRequests int64
	errorCount       int64
	downstreamURL    string
	httpClient       *http.Client
)

func queryInt(r *http.Request, name string, def int) int {
	if v := r.URL.Query().Get(name); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 0 {
			return n
		}
	}
	return def
}

func recordPeakGoroutines() {
	if g := int64(runtime.NumGoroutine()); g > atomic.LoadInt64(&peakGoroutines) {
		atomic.StoreInt64(&peakGoroutines, g)
	}
}

// delayHandler simulates a slow downstream dependency (DB, remote API, etc).
func delayHandler(w http.ResponseWriter, r *http.Request) {
	ms := queryInt(r, "ms", 50)
	time.Sleep(time.Duration(ms) * time.Millisecond)
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{}{"sleptMs": ms})
}

func ioHandler(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	atomic.AddInt64(&inFlightRequests, 1)
	defer atomic.AddInt64(&inFlightRequests, -1)

	delayMs := queryInt(r, "delayMs", 50)
	calls := queryInt(r, "calls", 1)
	if calls > 100 {
		calls = 100
	}
	if calls < 1 {
		calls = 1
	}

	var wg sync.WaitGroup
	var localErrors int64

	for i := 0; i < calls; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			url := fmt.Sprintf("%s/delay?ms=%d", downstreamURL, delayMs)
			resp, err := httpClient.Get(url)
			if err != nil {
				atomic.AddInt64(&localErrors, 1)
				atomic.AddInt64(&errorCount, 1)
				return
			}
			_, _ = io.Copy(io.Discard, resp.Body)
			_ = resp.Body.Close()
		}()
	}
	wg.Wait()

	elapsed := time.Since(start)
	atomic.AddInt64(&totalRequests, 1)
	atomic.AddInt64(&totalDurationNs, elapsed.Nanoseconds())
	recordPeakGoroutines()

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"workload":   "io",
		"delayMs":    delayMs,
		"calls":      calls,
		"errors":     localErrors,
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
	fmt.Fprintf(w, "# HELP app_errors_total Total downstream call errors\n# TYPE app_errors_total counter\napp_errors_total %d\n", atomic.LoadInt64(&errorCount))
	fmt.Fprintf(w, "# HELP app_inflight_requests Requests currently being served\n# TYPE app_inflight_requests gauge\napp_inflight_requests %d\n", atomic.LoadInt64(&inFlightRequests))
	fmt.Fprintf(w, "# HELP app_goroutines Current number of goroutines\n# TYPE app_goroutines gauge\napp_goroutines %d\n", runtime.NumGoroutine())
	fmt.Fprintf(w, "# HELP app_peak_goroutines Peak observed goroutines\n# TYPE app_peak_goroutines gauge\napp_peak_goroutines %d\n", atomic.LoadInt64(&peakGoroutines))
	fmt.Fprintf(w, "# HELP app_heap_alloc_bytes Heap memory currently allocated\n# TYPE app_heap_alloc_bytes gauge\napp_heap_alloc_bytes %d\n", m.HeapAlloc)
	fmt.Fprintf(w, "# HELP app_num_cpu Logical CPUs visible to the process\n# TYPE app_num_cpu gauge\napp_num_cpu %d\n", runtime.NumCPU())
}

func statsLogger() {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()
	for range ticker.C {
		var m runtime.MemStats
		runtime.ReadMemStats(&m)
		log.Printf("[stats] goroutines=%d peakGoroutines=%d inFlight=%d heapAllocMB=%.2f totalRequests=%d errors=%d gomaxprocs=%d",
			runtime.NumGoroutine(), atomic.LoadInt64(&peakGoroutines), atomic.LoadInt64(&inFlightRequests),
			float64(m.HeapAlloc)/1024/1024, atomic.LoadInt64(&totalRequests), atomic.LoadInt64(&errorCount), runtime.GOMAXPROCS(0))
	}
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	downstreamURL = os.Getenv("DOWNSTREAM_URL")
	if downstreamURL == "" {
		downstreamURL = "http://localhost:" + port
	}

	httpClient = &http.Client{
		Timeout: 10 * time.Second,
		Transport: &http.Transport{
			MaxIdleConns:        10000,
			MaxIdleConnsPerHost: 10000,
			IdleConnTimeout:     90 * time.Second,
		},
	}

	go statsLogger()

	mux := http.NewServeMux()
	mux.HandleFunc("/io", ioHandler)
	mux.HandleFunc("/delay", delayHandler)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	mux.HandleFunc("/metrics", metricsHandler)

	log.Printf("go-network listening on :%s downstream=%s gomaxprocs=%d", port, downstreamURL, runtime.GOMAXPROCS(0))
	log.Fatal(http.ListenAndServe(":"+port, mux))
}
