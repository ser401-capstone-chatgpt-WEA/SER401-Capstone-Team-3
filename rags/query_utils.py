"""
Utility functions for query preprocessing in the RAG pipeline.
"""
import re
from typing import List

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

# Example usage
if __name__ == "__main__":
    raw_query = "   What is the WEATHER ALERT for Phoenix??!!   "
    print("Raw Query:", raw_query)
    print("Processed Query:", preprocess_query(raw_query))