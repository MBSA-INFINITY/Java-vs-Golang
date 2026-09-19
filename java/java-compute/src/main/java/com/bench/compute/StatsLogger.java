package com.bench.compute;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

/**
 * Periodically logs JVM/thread stats. platformThreads stays low/flat under virtual-thread
 * concurrency - that flatness itself is the interesting comparison point against Go's goroutine count.
 */
@Component
public class StatsLogger {

    private static final Logger log = LoggerFactory.getLogger(StatsLogger.class);
    private static final ThreadMXBean threadBean = ManagementFactory.getThreadMXBean();

    @Scheduled(fixedRate = 5000)
    public void logStats() {
        Runtime rt = Runtime.getRuntime();
        long usedMb = (rt.totalMemory() - rt.freeMemory()) / (1024 * 1024);
        log.info("[stats] inFlight={} platformThreads={} peakPlatformThreads={} heapUsedMB={} totalRequests={} availableProcessors={}",
                AppMetrics.inFlightRequests.get(),
                threadBean.getThreadCount(),
                threadBean.getPeakThreadCount(),
                usedMb,
                AppMetrics.totalRequests.get(),
                rt.availableProcessors());
    }
}
