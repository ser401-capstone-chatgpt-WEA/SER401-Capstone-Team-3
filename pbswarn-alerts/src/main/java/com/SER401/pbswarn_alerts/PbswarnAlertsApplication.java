package com.SER401.pbswarn_alerts;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class PbswarnAlertsApplication {
	public static void main(String[] args) {
		SpringApplication.run(PbswarnAlertsApplication.class, args);
	}
}
