"""
Semantic retrieval wrapper for PBS WARN RAG system.
"""
import logging
import os
from typing import List, Dict, Any, Optional
from chroma_setup import ChromaDBManager

# Configure logging to use absolute path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
log_file_path = os.path.join(project_root, 'pbs_warn_scraper.log')
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)



DEFAULT_MIN_SCORE = 0.25


class AlertRetriever:
    """Handles semantic search against Chroma vector store."""
    
    def __init__(
        self,
        chroma_path: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chroma_db"),
        collection_name: str = "pbs_warn_alerts",
        min_score: float = DEFAULT_MIN_SCORE
    ):
        self.db = ChromaDBManager(
            persist_directory=chroma_path,
            collection_name=collection_name
        )
        self.min_score = min_score
        logging.info(f"Initialized retriever with {self.db.collection.count()} documents, min_score={min_score}")
    
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        min_score: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant alerts for a query, filtering by minimum similarity score.
        
        Args:
            query: Natural language query string
            top_k: Number of documents to retrieve
            filters: Optional metadata filters (e.g., {"severity": "Severe"})
            min_score: Minimum similarity score (0-1) to include. Defaults to instance setting.
        
        Returns:
            List of dicts with keys: id, text, metadata, score
        """
        threshold = min_score if min_score is not None else self.min_score

        try:
            results = self.db.query(
                query_texts=[query],
                n_results=top_k,
                where=filters
            )
            
            # Flatten Chroma's nested structure and apply score threshold
            retrieved = []
            for i in range(len(results['ids'][0])):
                score = 1.0 - results['distances'][0][i]  # Convert distance to similarity
                if score < threshold:
                    continue
                retrieved.append({
                    'id': results['ids'][0][i],
                    'text': results['documents'][0][i],
                    'metadata': results['metadatas'][0][i],
                    'score': score
                })
            
            logging.info(
                f"Retrieved {len(retrieved)} documents (threshold={threshold}) "
                f"for query: {query[:50]}..."
            )
            return retrieved
            
        except Exception as e:
            logging.error(f"Retrieval error: {e}")
            return []
