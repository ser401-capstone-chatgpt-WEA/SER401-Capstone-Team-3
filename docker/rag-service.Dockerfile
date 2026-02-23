FROM python:3.11-slim

WORKDIR /app

## TODO: Split requirements.txt into domain-specific files?
# Currently installs scraper deps unnecessarily (~300MB overhead)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN apt update \
    && apt install -y curl

# Pre-download and cache the embedding model
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# Copy RAG modules and dependencies
COPY rags/ ./rags/
COPY chroma_setup.py .
COPY pbs_warn_utils.py .

# Expose API port
EXPOSE 8000

# Mount point for Chroma DB
VOLUME /app/chroma_db

# Run FastAPI service
CMD ["uvicorn", "rags.service:app", "--host", "0.0.0.0", "--port", "8000"]
