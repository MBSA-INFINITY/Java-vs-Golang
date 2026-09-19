package com.bench.network;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class JavaNetworkApplication {
    public static void main(String[] args) {
        SpringApplication.run(JavaNetworkApplication.class, args);
    }
}
