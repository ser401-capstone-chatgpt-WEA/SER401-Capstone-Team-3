"""
Custom exception classes for the PBS WARN RAG service.

This module defines specific exception types for different error scenarios
in the RAG pipeline, enabling more granular error handling and clearer
error messages for API consumers.
"""
from fastapi import HTTPException


class RAGServiceError(Exception):
    """Base exception for all RAG service errors."""
    
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class QueryValidationError(RAGServiceError):
    """
    Raised when query validation fails.
    
    Examples:
        - Empty query
        - Query too short or too long
        - Prohibited patterns detected (SQL injection attempts)
        - Invalid characters in query
    """
    
    def __init__(self, message: str):
        super().__init__(message, status_code=400)


class RetrieverError(RAGServiceError):
    """
    Raised when document retrieval fails.
    
    Examples:
        - Vector database connection failure
        - Collection not found
        - Query embedding generation failure
        - Timeout during retrieval
    """
    
    def __init__(self, message: str):
        super().__init__(message, status_code=503)


class GeneratorError(RAGServiceError):
    """
    Raised when response generation fails.
    
    Examples:
        - LLM API connection failure
        - API key invalid or expired
        - Rate limit exceeded
        - Model unavailable
        - Response generation timeout
    """
    
    def __init__(self, message: str):
        super().__init__(message, status_code=503)


class RateLimitExceededError(RAGServiceError):
    """
    Raised when a client exceeds the rate limit.
    
    Attributes:
        retry_after: Seconds until the client can retry
    """
    
    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(message, status_code=429)


class CacheError(RAGServiceError):
    """
    Raised when cache operations fail.
    
    Examples:
        - Cache read/write failure
        - Serialization errors
        - Cache capacity exceeded
    """
    
    def __init__(self, message: str):
        super().__init__(message, status_code=500)


def rag_exception_to_http(exc: RAGServiceError) -> HTTPException:
    """
    Convert a RAGServiceError to an HTTPException.
    
    Args:
        exc: The RAG service exception to convert
    
    Returns:
        HTTPException with appropriate status code and detail message
    """
    return HTTPException(status_code=exc.status_code, detail=exc.message)
