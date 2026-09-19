package com.bench.compute;

import java.util.concurrent.atomic.AtomicLong;

/** Shared in-process counters, mirrored by the Go service for an apples-to-apples /metrics comparison. */
public final class AppMetrics {
    public static final AtomicLong totalRequests = new AtomicLong();
    public static final AtomicLong totalDurationNs = new AtomicLong();
    public static final AtomicLong inFlightRequests = new AtomicLong();
    public static final AtomicLong errorCount = new AtomicLong();

    private AppMetrics() {
    }
}
