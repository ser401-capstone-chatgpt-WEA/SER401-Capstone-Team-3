FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt update \
    && apt install -y curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download and cache the embedding model
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# Copy all application code
COPY *.py ./
COPY rags/ ./rags/

# Expose API port
EXPOSE 8000

# Health check for Docker
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Run unified entrypoint (starts both FastAPI and scheduler)
CMD ["python3", "entrypoint.py"]