package com.bench.compute;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

@RestController
public class ComputeController {

    // One virtual thread per submitted task - the Java 21 analogue of a Go goroutine.
    private static final ExecutorService VIRTUAL_EXECUTOR = Executors.newVirtualThreadPerTaskExecutor();

    // Deliberately naive O(sqrt(n)) trial-division primality test - CPU heavy by design, identical to the Go version.
    private static boolean isPrime(int n) {
        if (n < 2) return false;
        for (int i = 2; (long) i * i <= n; i++) {
            if (n % i == 0) return false;
        }
        return true;
    }

    private static int countPrimesInRange(int lo, int hi) {
        int count = 0;
        for (int i = lo; i < hi; i++) {
            if (isPrime(i)) count++;
        }
        return count;
    }

    @GetMapping("/compute")
    public Map<String, Object> compute(@RequestParam(defaultValue = "200000") int limit,
                                        @RequestParam(defaultValue = "1") int workers) throws Exception {
        long start = System.nanoTime();
        AppMetrics.inFlightRequests.incrementAndGet();
        try {
            if (workers > 4096) workers = 4096;
            if (workers > limit) workers = Math.max(1, limit);

            int chunk = limit / workers;
            List<Future<Integer>> futures = new ArrayList<>(workers);
            for (int w = 0; w < workers; w++) {
                int lo = w * chunk;
                int hi = (w == workers - 1) ? limit : lo + chunk;
                futures.add(VIRTUAL_EXECUTOR.submit(() -> countPrimesInRange(lo, hi)));
            }

            int total = 0;
            for (Future<Integer> f : futures) {
                total += f.get();
            }

            long elapsedNs = System.nanoTime() - start;
            AppMetrics.totalRequests.incrementAndGet();
            AppMetrics.totalDurationNs.addAndGet(elapsedNs);

            Map<String, Object> resp = new HashMap<>();
            resp.put("workload", "compute");
            resp.put("limit", limit);
            resp.put("workers", workers);
            resp.put("primeCount", total);
            resp.put("durationMs", elapsedNs / 1_000_000.0);
            resp.put("inFlightRequests", AppMetrics.inFlightRequests.get());
            return resp;
        } finally {
            AppMetrics.inFlightRequests.decrementAndGet();
        }
    }

    @GetMapping("/healthz")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }
}
