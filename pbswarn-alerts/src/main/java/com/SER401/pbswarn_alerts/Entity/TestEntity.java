package com.SER401.pbswarn_alerts.Entity;

import lombok.Data;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import jakarta.validation.constraints.NotBlank;
import org.springframework.data.mongodb.core.mapping.Field;

@Data
@Document("pbs_alerts")
public class TestEntity {
  @Id
  private String id;

  @NotBlank
  @Field("alertTitle")
  private String alertTitle;

  @NotBlank
  @Field("alertDetails")
  private String alertDetails;
}
