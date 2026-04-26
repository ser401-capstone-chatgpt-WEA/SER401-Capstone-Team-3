import json
import os

alerts_dir = "pbs_warn_outputs"
if not os.path.exists(alerts_dir):
    os.makedirs(alerts_dir)
    
file_path = os.path.join(alerts_dir, "pbs_warn_alerts_demo.json")

alert_data = {
  "alerts": [
    {
      "Message_ID": "DEMO-TORNADO-PDS-777",
      "Sender": "National Weather Service",
      "Sent_Time": "2026-04-12T19:00:00Z",
      "Status": "Actual",
      "Message_Type": "Alert",
      "Category": "Met",
      "Severity": "Extreme",
      "Certainty": "Observed",
      "Urgency": "Immediate",
      "Event": "Tornado Warning",
      "Area_Description": "Phoenix, Arizona; Scottsdale, Arizona",
      "Message_Text": "TORNADO WARNING in effect for Phoenix and Scottsdale, Arizona. Take cover immediately! A large, extremely dangerous tornado has been confirmed on the ground. This is a PARTICULARLY DANGEROUS SITUATION (PDS). Flying debris will be deadly to those caught without shelter.",
      "latitude": 33.4484,
      "longitude": -112.074,
      "radius_km": 50
    }
  ]
}

with open(file_path, "w") as f:
    json.dump(alert_data, f, indent=4)

os.makedirs("data", exist_ok=True)
with open("data/cleaned_alerts.json", "w") as f:
    # Deterministic tools expect a flat array, not wrapped in 'alerts'
    json.dump(alert_data["alerts"], f, indent=4)

print(f"✅ Created mock alert file explicitly at {file_path}")
print(f"✅ Created explicit deterministic mirror at data/cleaned_alerts.json")

print("🚀 Ingesting alert securely into Chroma Vector DB...")
try:
    from rags.ingest_alerts import ingest_folder
    ingest_folder(input_folder=alerts_dir, file_pattern="pbs_warn_alerts_demo.json")
    print("\n✅ Ingestion globally complete! The alert is now live in the RAG system.")
    print("👉 Tell Claude: 'Summarize the current weather alerts in Phoenix, Arizona'")
except Exception as e:
    print(f"\n❌ Failed to ingest alert natively: {e}")
