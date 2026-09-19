package com.bench.diskio;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

/**
 * Periodically logs JVM/thread stats. platformThreads stays low/flat even under
 * heavy inFlight disk-IO concurrency - the same virtual-thread flatness observed
 * in the network service, worth comparing side by side.
 */
@Component
public class StatsLogger {

    private static final Logger log = LoggerFactory.getLogger(StatsLogger.class);
    private static final ThreadMXBean threadBean = ManagementFactory.getThreadMXBean();

    @Scheduled(fixedRate = 5000)
    public void logStats() {
        Runtime rt = Runtime.getRuntime();
        long usedMb = (rt.totalMemory() - rt.freeMemory()) / (1024 * 1024);
        log.info("[stats] inFlight={} platformThreads={} peakPlatformThreads={} heapUsedMB={} totalRequests={} bytesWritten={} bytesRead={} errors={} availableProcessors={}",
                AppMetrics.inFlightRequests.get(),
                threadBean.getThreadCount(),
                threadBean.getPeakThreadCount(),
                usedMb,
                AppMetrics.totalRequests.get(),
                AppMetrics.totalBytesWritten.get(),
                AppMetrics.totalBytesRead.get(),
                AppMetrics.errorCount.get(),
                rt.availableProcessors());
    }
}
