package com.SER401.pbswarn_alerts.Controller;

import com.SER401.pbswarn_alerts.Repository.AlertRepository;
import com.SER401.pbswarn_alerts.Entity.Alert;
import com.SER401.pbswarn_alerts.Reader.FileReader;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
@RequestMapping("/alerts")
public class AlertController {
  @Autowired
  private final AlertRepository testRepository;

  @Autowired
  private FileReader fileReader;

  public AlertController(AlertRepository testRepository) {
    this.testRepository = testRepository;
  }

  @SuppressWarnings("null")
  @PostMapping
  public ResponseEntity<Alert> post(@Valid @RequestBody Alert testEntity) {
    return ResponseEntity.ok(testRepository.save(testEntity));
  }

  @SuppressWarnings("null")
  @PostMapping("/load-alerts")
  public List<Alert> loadAlerts() {
    List<Alert> alerts = fileReader.readAlerts();
    return testRepository.saveAll(alerts);
  }

  @GetMapping
  public List<Alert> getAll() {
    return testRepository.findAll();
  }

  @SuppressWarnings("null")
  @GetMapping("/{id}")
  public ResponseEntity<Alert> get(@PathVariable String id) {
    return testRepository.findById(id).map(ResponseEntity::ok).orElse(ResponseEntity.notFound().build());
  }
}
