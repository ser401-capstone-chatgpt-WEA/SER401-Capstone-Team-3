## Run Docker Container set for "scrape_pos_warn_apı.py" for now

docker compose -f docker/docker-compose.yml up -d

## RAG Service

### Run Locally
Ensure that the Python path is setup properly for local imports
```shell
export PYTHONPATH=$PYTHONPATH:$(pwd)
```

### Documentation

- View Swagger UI: http://localhost:8000/docs
- View ReDoc: http://localhost:8000/redoc

Run this in one session
```python
python -m uvicorn rags.service:app --reload
```
Quick temp test that it's working (run in another session)
```shell
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What severe weather alerts are active?", "top_k": 3}' \
  | jq '.formatted_summary' -r
```

Run tests
```shell
# be in rags/ directory when running locally
pytest -vv -rA --run-llm-tests --showlocals
```

### Rag Container
Run same command for starting services
```shell
docker compose -f docker/docker-compose.yml up -d
```

Go into container and run same local tests
```shell
# Exec into it (replace with actual name/container id)
docker exec -it rag-1_id bash

# Inside the container, test the API
curl http://localhost:8000/health
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What severe weather alerts are active?", "top_k": 3}' \
  | jq '.formatted_summary' -r

# Run tests
python rags/test_service.py
```

## Health Monitoring

Use the monitor script to check scraper freshness and the RAG service health endpoint.

Basic usage:
```shell
python monitor.py
```

Customize thresholds and URL:
```shell
python monitor.py --health-url http://localhost:8000/health --max-age-minutes 40
```

JSON output for integrations:
```shell
python monitor.py --json
```
```