"""
FastAPI RAG service for PBS WARN alerts.
"""
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import logging
import os

from rags.retriever import AlertRetriever
from rags.generator import ResponseGenerator

# Configure logging to use absolute path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
log_file_path = os.path.join(project_root, 'pbs_warn_scraper.log')
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = FastAPI(
    title="PBS WARN RAG Service",
    description="Retrieval-Augmented Generation service for PBS WARN emergency alerts",
    version="1.0.0"
)

# Initialize components
retriever = AlertRetriever()
generator = ResponseGenerator()


class QueryRequest(BaseModel):
    query: str = Field(..., description="Natural language query about emergency alerts")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of documents to retrieve")
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Optional metadata filters")


class Source(BaseModel):
    id: str
    score: float
    metadata: Dict[str, Any]


class QueryResponse(BaseModel):
    answer: str
    sources: List[Source]
    tokens_used: int = 0
    latency_ms: Dict[str, float] = Field(default_factory=dict, description="Per-stage latency in milliseconds")


@app.post("/query", response_model=QueryResponse)
async def query_rag(request: QueryRequest):
    """
    Query the RAG system for alert information.
    
    Args:
        request: Query request with natural language question
    
    Returns:
        Grounded answer with source citations and per-stage latency
    """
    try:
        total_start = time.perf_counter()
        logging.info(f"Received query: {request.query}")
        
        # Retrieve relevant documents
        retrieval_start = time.perf_counter()
        retrieved = retriever.retrieve(
            query=request.query,
            top_k=request.top_k,
            filters=request.filters
        )
        retrieval_ms = (time.perf_counter() - retrieval_start) * 1000
        
        # Generate grounded response
        generation_start = time.perf_counter()
        response = generator.generate(
            query=request.query,
            retrieved_docs=retrieved
        )
        generation_ms = (time.perf_counter() - generation_start) * 1000
        
        total_ms = (time.perf_counter() - total_start) * 1000

        latency_ms = {
            "retrieval_ms": round(retrieval_ms, 2),
            "generation_ms": round(generation_ms, 2),
            "total_ms": round(total_ms, 2),
        }

        logging.info(
            f"Query latency — retrieval: {retrieval_ms:.1f}ms, "
            f"generation: {generation_ms:.1f}ms, total: {total_ms:.1f}ms"
        )

        return QueryResponse(**response, latency_ms=latency_ms)
        
    except Exception as e:
        logging.error(f"Query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    """
    Health check endpoint.
    
    Returns:
        Service status and document count
    """
    try:
        stats = retriever.db.get_collection_stats()
        return {
            "status": "healthy",
            "documents_indexed": stats['document_count'],
            "collection_name": retriever.db.collection_name
        }
    except Exception as e:
        logging.error(f"Health check error: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "PBS WARN RAG API",
        "version": "1.0.0",
        "endpoints": {
            "query": "/query (POST)",
            "health": "/health (GET)",
            "docs": "/docs (GET)"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
