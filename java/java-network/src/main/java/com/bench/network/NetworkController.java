package com.bench.network;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

@RestController
public class NetworkController {

    // One virtual thread per outbound call/incoming request - the Java 21 analogue of a Go goroutine.
    private static final ExecutorService VIRTUAL_EXECUTOR = Executors.newVirtualThreadPerTaskExecutor();

    private static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .executor(VIRTUAL_EXECUTOR)
            .build();

    private static final String DOWNSTREAM_URL = resolveDownstreamUrl();

    private static String resolveDownstreamUrl() {
        String configured = System.getenv("DOWNSTREAM_URL");
        if (configured != null && !configured.isBlank()) {
            return configured;
        }
        String port = System.getenv().getOrDefault("PORT", "8080");
        return "http://localhost:" + port;
    }

    /** Simulates a slow downstream dependency (DB, remote API, etc). */
    @GetMapping("/delay")
    public Map<String, Object> delay(@RequestParam(defaultValue = "50") int ms) throws InterruptedException {
        Thread.sleep(ms);
        return Map.of("sleptMs", ms);
    }

    @GetMapping("/io")
    public Map<String, Object> io(@RequestParam(defaultValue = "50") int delayMs,
                                   @RequestParam(defaultValue = "1") int calls) {
        long start = System.nanoTime();
        AppMetrics.inFlightRequests.incrementAndGet();
        try {
            int actualCalls = Math.max(1, Math.min(calls, 100));
            List<Future<Void>> futures = new ArrayList<>(actualCalls);
            for (int i = 0; i < actualCalls; i++) {
                futures.add(VIRTUAL_EXECUTOR.submit(() -> {
                    callDownstream(delayMs);
                    return null;
                }));
            }

            int errors = 0;
            for (Future<Void> f : futures) {
                try {
                    f.get();
                } catch (ExecutionException | InterruptedException e) {
                    errors++;
                    AppMetrics.errorCount.incrementAndGet();
                }
            }

            long elapsedNs = System.nanoTime() - start;
            AppMetrics.totalRequests.incrementAndGet();
            AppMetrics.totalDurationNs.addAndGet(elapsedNs);

            Map<String, Object> resp = new HashMap<>();
            resp.put("workload", "io");
            resp.put("delayMs", delayMs);
            resp.put("calls", actualCalls);
            resp.put("errors", errors);
            resp.put("durationMs", elapsedNs / 1_000_000.0);
            resp.put("inFlightRequests", AppMetrics.inFlightRequests.get());
            return resp;
        } finally {
            AppMetrics.inFlightRequests.decrementAndGet();
        }
    }

    private void callDownstream(int delayMs) {
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(DOWNSTREAM_URL + "/delay?ms=" + delayMs))
                    .timeout(Duration.ofSeconds(10))
                    .GET()
                    .build();
            HttpResponse<Void> response = HTTP_CLIENT.send(request, HttpResponse.BodyHandlers.discarding());
            if (response.statusCode() != 200) {
                throw new RuntimeException("downstream returned status " + response.statusCode());
            }
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    @GetMapping("/healthz")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }
}
