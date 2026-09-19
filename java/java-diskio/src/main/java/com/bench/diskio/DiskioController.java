package com.bench.diskio;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicLong;

@RestController
public class DiskioController {

    public static class Record {
        public int id;
        public String name;
        public double value;
        public boolean active;
        public List<String> tags;
    }

    private static final class CycleResult {
        int count;
        double checksum;
        long bytesWritten;
        long bytesRead;
    }

    // One virtual thread per independent write+fsync+read+decode cycle - the Java 21 analogue of a Go goroutine.
    private static final ExecutorService VIRTUAL_EXECUTOR = Executors.newVirtualThreadPerTaskExecutor();
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final AtomicLong FILE_COUNTER = new AtomicLong();
    private static final String DISKIO_DIR = resolveDiskioDir();

    private static String resolveDiskioDir() {
        String configured = System.getenv("DISKIO_DIR");
        String dir = (configured != null && !configured.isBlank()) ? configured : System.getProperty("java.io.tmpdir");
        new File(dir).mkdirs();
        return dir;
    }

    private static List<Record> makeRecords(int n) {
        List<Record> records = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            Record r = new Record();
            r.id = i;
            r.name = "item-" + i;
            r.value = i * 1.5;
            r.active = i % 2 == 0;
            r.tags = List.of("tag-a", "tag-b");
            records.add(r);
        }
        return records;
    }

    // Deliberately writes a fresh file and fsyncs it, so this exercises real write+flush+read cost, not just page-cache reads.
    private static CycleResult writeReadDecode(int records) throws Exception {
        List<Record> data = makeRecords(records);
        byte[] payload = MAPPER.writeValueAsBytes(data);

        long id = FILE_COUNTER.incrementAndGet();
        File file = new File(DISKIO_DIR, "java-diskio-" + ProcessHandle.current().pid() + "-" + id + ".json");

        try (FileOutputStream fos = new FileOutputStream(file)) {
            fos.write(payload);
            fos.getFD().sync(); // force a real flush to disk, not just the page cache buffer
        }

        byte[] raw;
        try {
            raw = Files.readAllBytes(file.toPath());
        } finally {
            file.delete();
        }

        Record[] decoded = MAPPER.readValue(raw, Record[].class);

        double checksum = 0.0;
        for (Record r : decoded) {
            checksum += r.value;
        }

        CycleResult result = new CycleResult();
        result.count = decoded.length;
        result.checksum = checksum;
        result.bytesWritten = payload.length;
        result.bytesRead = raw.length;
        return result;
    }

    @GetMapping("/diskio")
    public Map<String, Object> diskio(@RequestParam(defaultValue = "1000") int records,
                                       @RequestParam(defaultValue = "1") int workers) {
        long start = System.nanoTime();
        AppMetrics.inFlightRequests.incrementAndGet();
        try {
            if (workers > 256) workers = 256;

            List<Future<CycleResult>> futures = new ArrayList<>(workers);
            for (int w = 0; w < workers; w++) {
                futures.add(VIRTUAL_EXECUTOR.submit(() -> writeReadDecode(records)));
            }

            int totalCount = 0;
            double totalChecksum = 0.0;
            long bytesW = 0, bytesR = 0;
            int failed = 0;
            for (Future<CycleResult> f : futures) {
                try {
                    CycleResult r = f.get();
                    totalCount += r.count;
                    totalChecksum += r.checksum;
                    bytesW += r.bytesWritten;
                    bytesR += r.bytesRead;
                } catch (Exception e) {
                    failed++;
                    AppMetrics.errorCount.incrementAndGet();
                }
            }

            long elapsedNs = System.nanoTime() - start;
            AppMetrics.totalRequests.incrementAndGet();
            AppMetrics.totalDurationNs.addAndGet(elapsedNs);
            AppMetrics.totalBytesWritten.addAndGet(bytesW);
            AppMetrics.totalBytesRead.addAndGet(bytesR);

            Map<String, Object> resp = new HashMap<>();
            resp.put("workload", "diskio");
            resp.put("records", records);
            resp.put("workers", workers);
            resp.put("recordCount", totalCount);
            resp.put("checksum", totalChecksum);
            resp.put("bytesWritten", bytesW);
            resp.put("bytesRead", bytesR);
            resp.put("errors", failed);
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
