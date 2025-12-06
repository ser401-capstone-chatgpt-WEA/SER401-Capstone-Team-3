package com.SER401.pbswarn_alerts.Entity;

import lombok.Data;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import jakarta.validation.constraints.NotBlank;
import org.springframework.data.mongodb.core.mapping.Field;

@Data
@Document("pbs_alerts")
public class Alert {
  @Id
  private String id;

  @NotBlank
  @Field("event_type")
  private String event_type;

  @NotBlank
  @Field("status")
  private String status;

  @NotBlank
  @Field("description")
  private String description;

  @NotBlank
  @Field("sender")
  private String sender;

  @NotBlank
  @Field("severity")
  private String severity;

  @NotBlank
  @Field("issued")
  private String issued;

  @NotBlank
  @Field("expires")
  private String expires;
}
