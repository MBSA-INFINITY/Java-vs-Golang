package com.bench.diskio;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class JavaDiskioApplication {
    public static void main(String[] args) {
        SpringApplication.run(JavaDiskioApplication.class, args);
    }
}
