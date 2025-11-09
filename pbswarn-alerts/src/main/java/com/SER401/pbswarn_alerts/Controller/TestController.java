package com.SER401.pbswarn_alerts.Controller;

import com.SER401.pbswarn_alerts.Repository.TestRepository;
import com.SER401.pbswarn_alerts.Entity.TestEntity;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
@RequestMapping("/alerts")
public class TestController {
  private final TestRepository testRepository;

  public TestController(TestRepository testRepository) {
    this.testRepository = testRepository;
  }

  @SuppressWarnings("null")
  @PostMapping
  public ResponseEntity<TestEntity> post(@Valid @RequestBody TestEntity testEntity) {
    return ResponseEntity.ok(testRepository.save(testEntity));
  }

  @GetMapping
  public List<TestEntity> getAll() {
    return testRepository.findAll();
  }

  @GetMapping("/{id}")
  public ResponseEntity<TestEntity> get(@PathVariable String id) {
    return testRepository.findById(id).map(ResponseEntity::ok).orElse(ResponseEntity.notFound().build());
  }
}
