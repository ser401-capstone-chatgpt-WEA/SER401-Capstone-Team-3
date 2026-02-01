"""
FastAPI RAG service for PBS WARN alerts.
"""
from fastapi import FastAPI, HTTPException, Request, Query
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import logging
import re

from rags.retriever import AlertRetriever
from rags.generator import ResponseGenerator
from rags.query_utils import preprocess_query

logging.basicConfig(
    filename='pbs_warn_scraper.log',
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


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Log incoming requests and their responses.
    """
    logging.info(f"Incoming request: {request.method} {request.url}")
    response = await call_next(request)
    logging.info(f"Response status: {response.status_code}")
    return response


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


def validate_query(query: str):
    """
    Validate the query string.

    Args:
        query: The query string to validate.

    Raises:
        HTTPException: If the query is invalid.
    """
    if not query or len(query.strip()) == 0:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    if len(query) > 1000:
        raise HTTPException(status_code=400, detail="Query exceeds maximum length of 1,000 characters.")
    if len(query) < 3:
        raise HTTPException(status_code=400, detail="Query must be at least 3 characters long.")

    # Check for prohibited characters or patterns
    prohibited_patterns = [r"DROP TABLE", r"--", r";"]
    for pattern in prohibited_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            raise HTTPException(status_code=400, detail="Query contains prohibited patterns or characters.")

    # Ensure query contains only allowed characters
    if not re.match(r"^[a-zA-Z0-9 .,?!'\"-]+$", query):
        raise HTTPException(status_code=400, detail="Query contains unsupported characters.")


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
        # Preprocess the query
        processed_query = preprocess_query(request.query)
        logging.info(f"Processed query: {processed_query}")

        # Validate the query
        validate_query(processed_query)
        logging.info(f"Query parameters: top_k={request.top_k}, filters={request.filters}")
        
        # Retrieve relevant documents
        retrieved = retriever.retrieve(
            query=processed_query,
            top_k=request.top_k,
            filters=request.filters
        )
        logging.info(f"Retrieved {len(retrieved)} documents")
        
        # Generate grounded response
        response = generator.generate(
            query=processed_query,
            retrieved_docs=retrieved
        )
        logging.info("Generated response successfully")
        
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
