// go-diskio is a disk-IO-bound benchmark service.
//
// /diskio writes `workers` independent JSON files to disk (each containing
// `records` generated records), fsyncs them to force a real flush past the
// page cache, reads them back, and unmarshals them - deliberately exercising
// write+fsync+read+decode cost rather than pure in-memory work, so it can be
// compared against the compute and network workloads using the same
// concurrency-ramp methodology.
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"sync"
	"sync/atomic"
	"time"
)

type Record struct {
	ID     int      `json:"id"`
	Name   string   `json:"name"`
	Value  float64  `json:"value"`
	Active bool     `json:"active"`
	Tags   []string `json:"tags"`
}

var (
	totalRequests     int64
	totalDurationNs   int64
	peakGoroutines    int64
	totalBytesWritten int64
	totalBytesRead    int64
	errorCount        int64
	diskioDir         string
	fileCounter       int64
)

func queryInt(r *http.Request, name string, def int) int {
	if v := r.URL.Query().Get(name); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
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

func makeRecords(n int) []Record {
	records := make([]Record, n)
	for i := 0; i < n; i++ {
		records[i] = Record{
			ID:     i,
			Name:   fmt.Sprintf("item-%d", i),
			Value:  float64(i) * 1.5,
			Active: i%2 == 0,
			Tags:   []string{"tag-a", "tag-b"},
		}
	}
	return records
}

// writeReadDecode performs one full write+fsync+read+unmarshal cycle.
func writeReadDecode(records int) (count int, checksum float64, bytesWritten int64, bytesRead int64, err error) {
	data := makeRecords(records)
	payload, err := json.Marshal(data)
	if err != nil {
		return
	}

	id := atomic.AddInt64(&fileCounter, 1)
	path := filepath.Join(diskioDir, fmt.Sprintf("go-diskio-%d-%d.json", os.Getpid(), id))

	f, err := os.Create(path)
	if err != nil {
		return
	}
	defer os.Remove(path)

	n, err := f.Write(payload)
	if err != nil {
		f.Close()
		return
	}
	if err = f.Sync(); err != nil { // force a real flush to disk, not just the page cache buffer
		f.Close()
		return
	}
	if err = f.Close(); err != nil {
		return
	}

	raw, err := os.ReadFile(path)
	if err != nil {
		return
	}

	var decoded []Record
	if err = json.Unmarshal(raw, &decoded); err != nil {
		return
	}

	for _, rec := range decoded {
		checksum += rec.Value
	}
	count = len(decoded)
	bytesWritten = int64(n)
	bytesRead = int64(len(raw))
	return
}

func diskioHandler(w http.ResponseWriter, r *http.Request) {
	start := time.Now()

	records := queryInt(r, "records", 1000)
	workers := queryInt(r, "workers", 1)
	if workers > 256 {
		workers = 256
	}

	var wg sync.WaitGroup
	counts := make([]int, workers)
	sums := make([]float64, workers)
	written := make([]int64, workers)
	read := make([]int64, workers)
	errs := make([]error, workers)

	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			c, s, wb, rb, err := writeReadDecode(records)
			counts[idx], sums[idx], written[idx], read[idx], errs[idx] = c, s, wb, rb, err
		}(w)
	}
	wg.Wait()

	totalCount := 0
	totalSum := 0.0
	var bytesW, bytesR int64
	failed := 0
	for i := 0; i < workers; i++ {
		if errs[i] != nil {
			failed++
			atomic.AddInt64(&errorCount, 1)
			continue
		}
		totalCount += counts[i]
		totalSum += sums[i]
		bytesW += written[i]
		bytesR += read[i]
	}

	elapsed := time.Since(start)
	atomic.AddInt64(&totalRequests, 1)
	atomic.AddInt64(&totalDurationNs, elapsed.Nanoseconds())
	atomic.AddInt64(&totalBytesWritten, bytesW)
	atomic.AddInt64(&totalBytesRead, bytesR)
	recordPeakGoroutines()

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"workload":     "diskio",
		"records":      records,
		"workers":      workers,
		"recordCount":  totalCount,
		"checksum":     totalSum,
		"bytesWritten": bytesW,
		"bytesRead":    bytesR,
		"errors":       failed,
		"durationMs":   float64(elapsed.Microseconds()) / 1000.0,
		"goroutines":   runtime.NumGoroutine(),
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
	fmt.Fprintf(w, "# HELP app_errors_total Total write/read/decode errors\n# TYPE app_errors_total counter\napp_errors_total %d\n", atomic.LoadInt64(&errorCount))
	fmt.Fprintf(w, "# HELP app_bytes_written_total Total bytes written to disk\n# TYPE app_bytes_written_total counter\napp_bytes_written_total %d\n", atomic.LoadInt64(&totalBytesWritten))
	fmt.Fprintf(w, "# HELP app_bytes_read_total Total bytes read from disk\n# TYPE app_bytes_read_total counter\napp_bytes_read_total %d\n", atomic.LoadInt64(&totalBytesRead))
	fmt.Fprintf(w, "# HELP app_goroutines Current number of goroutines\n# TYPE app_goroutines gauge\napp_goroutines %d\n", runtime.NumGoroutine())
	fmt.Fprintf(w, "# HELP app_peak_goroutines Peak observed goroutines\n# TYPE app_peak_goroutines gauge\napp_peak_goroutines %d\n", atomic.LoadInt64(&peakGoroutines))
	fmt.Fprintf(w, "# HELP app_heap_alloc_bytes Heap memory currently allocated\n# TYPE app_heap_alloc_bytes gauge\napp_heap_alloc_bytes %d\n", m.HeapAlloc)
	fmt.Fprintf(w, "# HELP app_num_cpu Logical CPUs visible to the process\n# TYPE app_num_cpu gauge\napp_num_cpu %d\n", runtime.NumCPU())
	fmt.Fprintf(w, "# HELP app_gomaxprocs Current GOMAXPROCS setting\n# TYPE app_gomaxprocs gauge\napp_gomaxprocs %d\n", runtime.GOMAXPROCS(0))
}

func statsLogger() {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()
	for range ticker.C {
		var m runtime.MemStats
		runtime.ReadMemStats(&m)
		log.Printf("[stats] goroutines=%d peakGoroutines=%d heapAllocMB=%.2f totalRequests=%d bytesWritten=%d bytesRead=%d errors=%d gomaxprocs=%d",
			runtime.NumGoroutine(), atomic.LoadInt64(&peakGoroutines), float64(m.HeapAlloc)/1024/1024,
			atomic.LoadInt64(&totalRequests), atomic.LoadInt64(&totalBytesWritten), atomic.LoadInt64(&totalBytesRead),
			atomic.LoadInt64(&errorCount), runtime.GOMAXPROCS(0))
	}
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	diskioDir = os.Getenv("DISKIO_DIR")
	if diskioDir == "" {
		diskioDir = os.TempDir()
	}
	if err := os.MkdirAll(diskioDir, 0o755); err != nil {
		log.Fatalf("cannot create diskio dir %s: %v", diskioDir, err)
	}

	go statsLogger()

	mux := http.NewServeMux()
	mux.HandleFunc("/diskio", diskioHandler)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	mux.HandleFunc("/metrics", metricsHandler)

	log.Printf("go-diskio listening on :%s dir=%s (GOMAXPROCS=%d, NumCPU=%d)", port, diskioDir, runtime.GOMAXPROCS(0), runtime.NumCPU())
	log.Fatal(http.ListenAndServe(":"+port, mux))
}
