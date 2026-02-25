"""
Utility functions for query preprocessing in the RAG pipeline.
"""
import re
from collections import deque
from typing import List, Dict

# In-memory query history (limited to the last 100 queries)
query_history = deque(maxlen=100)

# Common abbreviations used in emergency alert queries
ABBREVIATIONS: Dict[str, str] = {
    "wx": "weather",
    "svr": "severe",
    "tstm": "thunderstorm",
    "tstrm": "thunderstorm",
    "wnd": "wind",
    "hvy": "heavy",
    "precip": "precipitation",
    "temp": "temperature",
    "govt": "government",
    "evac": "evacuation",
    "info": "information",
    "msg": "message",
    "pds": "particularly dangerous situation",
    "tor": "tornado",
    "ffw": "flash flood warning",
    "ffw": "flash flood watch",
    "svs": "severe weather statement",
}

# Common misspellings in alert-related queries
MISSPELLINGS: Dict[str, str] = {
    "torndo": "tornado",
    "torndao": "tornado",
    "hrricane": "hurricane",
    "hurrican": "hurricane",
    "floding": "flooding",
    "fllood": "flood",
    "ligthning": "lightning",
    "lightening": "lightning",
    "thunderstom": "thunderstorm",
    "earthquak": "earthquake",
    "tsunmai": "tsunami",
    "wildfie": "wildfire",
    "wildefire": "wildfire",
    "emergancy": "emergency",
    "wether": "weather",
    "wheather": "weather",
    "sevear": "severe",
    "sever": "severe",
    "warrning": "warning",
    "warnning": "warning",
}

# State abbreviation to full name mapping
STATE_ABBREVIATIONS: Dict[str, str] = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas",
    "ca": "california", "co": "colorado", "ct": "connecticut", "de": "delaware",
    "fl": "florida", "ga": "georgia", "hi": "hawaii", "id": "idaho",
    "il": "illinois", "in": "indiana", "ia": "iowa", "ks": "kansas",
    "ky": "kentucky", "la": "louisiana", "me": "maine", "md": "maryland",
    "ma": "massachusetts", "mi": "michigan", "mn": "minnesota", "ms": "mississippi",
    "mo": "missouri", "mt": "montana", "ne": "nebraska", "nv": "nevada",
    "nh": "new hampshire", "nj": "new jersey", "nm": "new mexico", "ny": "new york",
    "nc": "north carolina", "nd": "north dakota", "oh": "ohio", "ok": "oklahoma",
    "or": "oregon", "pa": "pennsylvania", "ri": "rhode island", "sc": "south carolina",
    "sd": "south dakota", "tn": "tennessee", "tx": "texas", "ut": "utah",
    "vt": "vermont", "va": "virginia", "wa": "washington", "wv": "west virginia",
    "wi": "wisconsin", "wy": "wyoming",
}

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

    # Expand abbreviations and fix misspellings
    words = query.split()
    processed_words = []
    for word in words:
        cleaned = word.strip(".,?!'\"")
        if cleaned in ABBREVIATIONS:
            processed_words.append(ABBREVIATIONS[cleaned])
        elif cleaned in MISSPELLINGS:
            processed_words.append(MISSPELLINGS[cleaned])
        elif cleaned in STATE_ABBREVIATIONS:
            processed_words.append(STATE_ABBREVIATIONS[cleaned])
        else:
            processed_words.append(word)

    query = " ".join(processed_words)

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