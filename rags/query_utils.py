"""
Utility functions for query preprocessing in the RAG pipeline.
"""
import re
from collections import deque
from typing import List

# In-memory query history (limited to the last 100 queries)
query_history = deque(maxlen=100)

def preprocess_query(query: str) -> str:
    """
    Preprocess the query string to normalize and clean it.

    Args:
        query: The raw query string.

    Returns:
        A cleaned and normalized query string.
    """
    # Convert to lowercase
    query = query.lower()

    # Remove extra whitespace
    query = re.sub(r"\s+", " ", query).strip()

    # Remove unsupported characters (keep alphanumeric and basic punctuation)
    query = re.sub(r"[^a-z0-9 .,?!'\"-]", "", query)

    return query

def store_query_history(query: str, parameters: dict, response: dict):
    """
    Store a query and its result in the history.

    Args:
        query: The processed query string.
        parameters: The query parameters (e.g., top_k, filters).
        response: The response generated for the query.
    """
    query_history.append({
        "query": query,
        "parameters": parameters,
        "response": response
    })

def get_query_history():
    """
    Retrieve the history of past queries and their results.

    Returns:
        List of past queries and their results.
    """
    return list(query_history)

# Example usage
if __name__ == "__main__":
    raw_query = "   What is the WEATHER ALERT for Phoenix??!!   "
    print("Raw Query:", raw_query)
    print("Processed Query:", preprocess_query(raw_query))