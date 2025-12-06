package com.SER401.pbswarn_alerts.Repository;

import org.springframework.data.mongodb.repository.MongoRepository;
import com.SER401.pbswarn_alerts.Entity.Alert;

public interface AlertRepository extends MongoRepository<Alert, String> {}
