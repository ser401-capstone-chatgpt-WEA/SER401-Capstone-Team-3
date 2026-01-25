"""
Semantic retrieval wrapper for PBS WARN RAG system.
"""
import logging
from typing import List, Dict, Any, Optional
from chroma_setup import ChromaDBManager

logging.basicConfig(
    filename='pbs_warn_scraper.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)



class AlertRetriever:
    """Handles semantic search against Chroma vector store."""
    
    def __init__(
        self,
        chroma_path: str = "./chroma_db",
        collection_name: str = "pbs_warn_alerts"
    ):
        self.db = ChromaDBManager(
            persist_directory=chroma_path,
            collection_name=collection_name
        )
        logging.info(f"Initialized retriever with {self.db.collection.count()} documents")
    
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant alerts for a query.
        
        Args:
            query: Natural language query string
            top_k: Number of documents to retrieve
            filters: Optional metadata filters (e.g., {"severity": "Severe"})
        
        Returns:
            List of dicts with keys: id, text, metadata, score
        """
        try:
            results = self.db.query(
                query_texts=[query],
                n_results=top_k,
                where=filters
            )
            
            # Flatten Chroma's nested structure
            retrieved = []
            for i in range(len(results['ids'][0])):
                retrieved.append({
                    'id': results['ids'][0][i],
                    'text': results['documents'][0][i],
                    'metadata': results['metadatas'][0][i],
                    'score': 1.0 - results['distances'][0][i]  # Convert distance to similarity
                })
            
            logging.info(f"Retrieved {len(retrieved)} documents for query: {query[:50]}...")
            return retrieved
            
        except Exception as e:
            logging.error(f"Retrieval error: {e}")
            return []
