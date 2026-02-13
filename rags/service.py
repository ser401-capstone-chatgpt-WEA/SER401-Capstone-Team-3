"""
FastAPI RAG service for PBS WARN alerts.
"""
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


@app.post("/query", response_model=QueryResponse)
async def query_rag(request: QueryRequest):
    """
    Query the RAG system for alert information.
    
    Args:
        request: Query request with natural language question
    
    Returns:
        Grounded answer with source citations
    """
    try:
        logging.info(f"Received query: {request.query}")
        
        # Retrieve relevant documents
        retrieved = retriever.retrieve(
            query=request.query,
            top_k=request.top_k,
            filters=request.filters
        )
        
        # Generate grounded response
        response = generator.generate(
            query=request.query,
            retrieved_docs=retrieved
        )
        
        return QueryResponse(**response)
        
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
