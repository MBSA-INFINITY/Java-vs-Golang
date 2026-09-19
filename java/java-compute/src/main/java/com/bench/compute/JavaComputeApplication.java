package com.bench.compute;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class JavaComputeApplication {
    public static void main(String[] args) {
        SpringApplication.run(JavaComputeApplication.class, args);
    }
}
