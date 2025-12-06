package com.SER401.pbswarn_alerts.Reader;

import java.io.InputStream;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import com.SER401.pbswarn_alerts.Entity.Alert;
import com.fasterxml.jackson.databind.ObjectMapper;

@Service
public class FileReader {
  @Autowired
  private ObjectMapper objectMapper;

  public List<Alert> readAlerts() {
    try {
      InputStream is = getClass().getResourceAsStream("/alerts.json");

      return objectMapper.readValue(
          is,
          objectMapper.getTypeFactory().constructCollectionType(List.class, Alert.class));

    } catch (Exception e) {
      throw new RuntimeException("File read error", e);
    }
  }
}
