package com.bench.diskio;

import io.micrometer.core.instrument.binder.MeterBinder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Exposes our custom counters through /actuator/prometheus alongside the built-in JVM/thread metrics. */
@Configuration
public class MetricsConfig {

    @Bean
    public MeterBinder appMetricsBinder() {
        return registry -> {
            registry.gauge("app_requests_total", AppMetrics.totalRequests);
            registry.gauge("app_inflight_requests", AppMetrics.inFlightRequests);
            registry.gauge("app_errors_total", AppMetrics.errorCount);
            registry.gauge("app_bytes_written_total", AppMetrics.totalBytesWritten);
            registry.gauge("app_bytes_read_total", AppMetrics.totalBytesRead);
        };
    }
}
