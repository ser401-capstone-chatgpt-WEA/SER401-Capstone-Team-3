"""
Chroma Vector Database Setup for PBS WARN RAG System

This module initializes and manages the Chroma vector database for storing
and retrieving PBS WARN alert embeddings using local sentence-transformers.
In the future, this can be adapted to use OpenAI API for embeddings.
"""

import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

# Configure logging following existing conventions
log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pbs_warn_scraper.log')
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Configuration
DEFAULT_CHROMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
DEFAULT_COLLECTION_NAME = "pbs_warn_alerts"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class ChromaDBManager:
    """
    Manages Chroma vector database operations for PBS WARN alerts.
    
    This class provides a self-contained interface for:
    - Initializing the vector database
    - Storing alert documents with embeddings
    - Retrieving relevant documents via semantic search
    - Managing collections and metadata
    """
    
    def __init__(
        self,
        persist_directory: str = DEFAULT_CHROMA_PATH,
        collection_name: str = DEFAULT_COLLECTION_NAME
    ):
        """
        Initialize Chroma database manager.
        
        Args:
            persist_directory: Path to persist Chroma data
            collection_name: Name of the collection to use
        """
        self.persist_directory = Path(persist_directory)
        self.collection_name = collection_name
        
        # Create persist directory
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize Chroma client
        self.client = self._initialize_client()
        
        # Initialize embedding function (local sentence-transformers)
        self.embedding_function = self._initialize_embedding_function()
        
        # Get or create collection
        self.collection = self._get_or_create_collection()
        
        logging.info(f"Initialized ChromaDB at {self.persist_directory}")
    
    def _initialize_client(self) -> chromadb.Client:
        """Initialize Chroma client with persistence (compat with 0.3.x)."""
        try:
            # For chromadb 0.3.x
            client = chromadb.Client(Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=str(self.persist_directory),
                anonymized_telemetry=False
            ))
            logging.info("Chroma client initialized successfully")
            return client
        except Exception as e:
            logging.error(f"Error initializing Chroma client: {e}")
            raise
    
    def _initialize_embedding_function(self):
        """Initialize sentence-transformers embedding function."""
        try:
            # Use Chroma's built-in sentence-transformers wrapper
            embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=EMBEDDING_MODEL
            )
            logging.info(f"Initialized embedding function with model: {EMBEDDING_MODEL}")
            return embedding_fn
        except Exception as e:
            logging.error(f"Error initializing embedding function: {e}")
            raise
    
    def _get_or_create_collection(self):
        """Get existing collection or create new one."""
        try:
            collection = self.client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_function,
                metadata={
                    "description": "PBS WARN emergency alerts",
                    "source": "PBS WARN API",
                    "embedding_model": EMBEDDING_MODEL
                }
            )
            logging.info(f"Collection '{self.collection_name}' ready with {collection.count()} documents")
            return collection
        except Exception as e:
            logging.error(f"Error getting/creating collection: {e}")
            raise
    
    def add_documents(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        ids: List[str]
    ) -> None:
        """
        Add documents to the vector database.
        
        Args:
            documents: List of document texts (alert content)
            metadatas: List of metadata dicts (alert fields)
            ids: List of unique document IDs (cap_identifier or generated)
        """
        try:
            if not documents or not metadatas or not ids:
                logging.warning("Empty documents, metadatas, or ids provided")
                return
            
            if not (len(documents) == len(metadatas) == len(ids)):
                raise ValueError("documents, metadatas, and ids must have same length")
            
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            
            logging.info(f"Added {len(documents)} documents to collection '{self.collection_name}'")
            
        except Exception as e:
            logging.error(f"Error adding documents to Chroma: {e}")
            raise
    
    def query(
        self,
        query_texts: List[str],
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Query the vector database for relevant documents.
        
        Args:
            query_texts: List of query strings (usually just one)
            n_results: Number of results to return (top_k)
            where: Metadata filters (e.g., {"severity": "Severe"})
            where_document: Document content filters
        
        Returns:
            Dict containing ids, documents, metadatas, and distances
        """
        try:
            results = self.collection.query(
                query_texts=query_texts,
                n_results=n_results,
                where=where,
                where_document=where_document
            )
            
            logging.info(f"Query returned {len(results['ids'][0])} results")
            return results
            
        except Exception as e:
            logging.error(f"Error querying Chroma: {e}")
            raise
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the collection."""
        try:
            count = self.collection.count()
            metadata = self.collection.metadata
            
            return {
                "collection_name": self.collection_name,
                "document_count": count,
                "metadata": metadata,
                "persist_directory": str(self.persist_directory)
            }
        except Exception as e:
            logging.error(f"Error getting collection stats: {e}")
            return {}
    
    def reset_collection(self) -> None:
        """
        Delete all documents from the collection.
        WARNING: This is destructive and cannot be undone.
        """
        try:
            self.client.delete_collection(name=self.collection_name)
            self.collection = self._get_or_create_collection()
            logging.warning(f"Collection '{self.collection_name}' has been reset")
        except Exception as e:
            logging.error(f"Error resetting collection: {e}")
            raise


def main():
    """
    Test the Chroma database setup.
    """
    try:
        # Initialize database
        db = ChromaDBManager()
        
        # Print stats
        stats = db.get_collection_stats()
        print("\n" + "="*80)
        print("Chroma Database Statistics")
        print("="*80)
        print(f"Collection Name: {stats['collection_name']}")
        print(f"Document Count: {stats['document_count']}")
        print(f"Persist Directory: {stats['persist_directory']}")
        print(f"Metadata: {stats.get('metadata', {})}")
        print("="*80)
        
        # Test document addition (using example data from test_pbs_warn_pipeline.py)
        test_docs = [
            "Local Area Emergency - MI_Iosco_County_Emergency_Management: Police activity near 22400 Cabin Branch Ave, Clarksburg. Residents should shelter-in-place.",
        ]
        test_metadata = [
            {
                "event": "Local Area Emergency",
                "title": "Local Area Emergency",
                "sender": "MI_Iosco_County_Emergency_Management",
                "severity": "Severe",
                "urgency": "Immediate",
                "certainty": "Observed",
                "status": "Actual",
                "cap_identifier": "17625290450001391722060",
                "message": "Police activity near 22400 Cabin Branch Ave, Clarksburg. Residents should shelter-in-place.",
                "expires": "2025-11-08T05:24:05+00:00"
            }
        ]
        test_ids = ["17625290450001391722060"]
        
        print("\nAdding test document...")
        db.add_documents(test_docs, test_metadata, test_ids)
        
        # Test query
        print("\nQuerying for 'emergency shelter'...")
        results = db.query(
            query_texts=["emergency shelter"],
            n_results=1
        )
        
        print("\nQuery Results:")
        print(f"Found {len(results['ids'][0])} documents")
        if results['ids'][0]:
            print(f"Top result ID: {results['ids'][0][0]}")
            print(f"Distance: {results['distances'][0][0]:.4f}")
            print(f"Content: {results['documents'][0][0][:100]}...")
        
        print("\n" + "="*80)
        print("Chroma setup test completed successfully!")
        print("="*80)
        
    except Exception as e:
        logging.error(f"Error in main: {e}")
        print(f"Error: {e}")
        raise


if __name__ == "__main__":
    main()