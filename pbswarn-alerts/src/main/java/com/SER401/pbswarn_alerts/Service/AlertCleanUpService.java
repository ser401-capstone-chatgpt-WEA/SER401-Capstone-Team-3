package com.SER401.pbswarn_alerts.Service;

import java.time.Instant;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import com.SER401.pbswarn_alerts.Entity.Alert;
import com.SER401.pbswarn_alerts.Repository.AlertRepository;

@Service
public class AlertCleanUpService {
  @Autowired
  private AlertRepository alertRepository;

  @Scheduled(fixedRate = 60_000)
  public void removeExpiredAlerts() {
    List<Alert> alerts = alertRepository.findAll();
    Instant now = Instant.now();
    for (Alert alert : alerts) {
      try {
        Instant expiresAt = Instant.parse(alert.getExpires());
        if (expiresAt.isBefore(now)) {
          alertRepository.delete(alert);
        }
      } catch (Exception e) {
        System.out.println("Bad date format: " + alert.getId());
      }
    }
  }
}
