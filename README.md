## Run Docker Container set for "scrape_pos_warn_apı.py" for now

docker compose -f docker/docker-compose.yml up -d

## RAG Service

### Run Locally
Run this in one session
```python
python -m uvicorn rags.service:app --reload
```
Quick temp test that it's working (run in another session)
```shell
curl -X POST http://localhost:8000/query \                        
  -H "Content-Type: application/json" \
  -d '{"query": "What severe weather alerts are active?", "top_k": 3}'
```