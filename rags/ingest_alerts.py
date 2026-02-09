"""
Alert Ingestion Pipeline for RAG System

Reads PBS WARN alert JSON files from pbs_warn_outputs and indexes them
into the Chroma vector database.
"""

import json
import logging
from pathlib import Path
from typing import List

from chroma_setup import ChromaDBManager
from rags.data_model import batch_map_alerts

# Configure logging to use absolute path
log_file_path = Path(__file__).resolve().parent.parent / 'pbs_warn_scraper.log'
logging.basicConfig(
    filename=str(log_file_path),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

DEFAULT_INPUT_FOLDER = './pbs_warn_outputs'
DEFAULT_CHROMA_PATH = str(Path(__file__).resolve().parent.parent / 'chroma_db')


def load_alerts_from_file(file_path: Path) -> List[dict]:
    """
    Load alerts from a PBS WARN JSON file.
    
    Args:
        file_path: Path to JSON file
    
    Returns:
        List of alert dicts
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle different JSON structures
        if isinstance(data, dict) and 'alerts' in data:
            alerts = data['alerts']
        elif isinstance(data, list):
            alerts = data
        else:
            logging.warning(f"Unexpected JSON structure in {file_path}")
            return []
        
        logging.info(f"Loaded {len(alerts)} alerts from {file_path.name}")
        return alerts
        
    except Exception as e:
        logging.error(f"Error loading {file_path}: {e}")
        return []


def ingest_file(
    file_path: Path,
    db_manager: ChromaDBManager,
    batch_size: int = 100
) -> int:
    """
    Ingest alerts from a single file into Chroma.
    
    Args:
        file_path: Path to JSON file
        db_manager: ChromaDBManager instance
        batch_size: Number of documents to ingest per batch
    
    Returns:
        Number of documents ingested
    """
    # Load alerts
    alerts = load_alerts_from_file(file_path)
    if not alerts:
        return 0
    
    # Map to RAGDocuments
    rag_docs = batch_map_alerts(alerts, source_file=file_path.name)
    if not rag_docs:
        return 0
    
    # Convert to Chroma format
    documents = []
    metadatas = []
    ids = []
    
    for doc in rag_docs:
        text, metadata, doc_id = doc.to_chroma_format()
        documents.append(text)
        metadatas.append(metadata)
        ids.append(doc_id)
    
    # Ingest in batches
    total_ingested = 0
    for i in range(0, len(documents), batch_size):
        batch_docs = documents[i:i+batch_size]
        batch_meta = metadatas[i:i+batch_size]
        batch_ids = ids[i:i+batch_size]
        
        try:
            db_manager.add_documents(batch_docs, batch_meta, batch_ids)
            total_ingested += len(batch_docs)
            logging.info(f"Ingested batch {i//batch_size + 1}: {len(batch_docs)} documents")
        except Exception as e:
            logging.error(f"Error ingesting batch: {e}")
            continue
    
    return total_ingested


def ingest_folder(
    input_folder: str = DEFAULT_INPUT_FOLDER,
    chroma_path: str = DEFAULT_CHROMA_PATH,
    file_pattern: str = "pbs_warn_alerts_*.json"
) -> None:
    """
    Ingest all alert files from a folder into Chroma.
    
    Args:
        input_folder: Folder containing JSON files
        chroma_path: Path to Chroma database
        file_pattern: Glob pattern for JSON files
    """
    logging.info(f"Starting ingestion from {input_folder}")
    
    # Initialize database
    db = ChromaDBManager(persist_directory=chroma_path)
    
    # Find all alert files
    input_path = Path(input_folder)
    json_files = sorted(input_path.glob(file_pattern))
    
    # Filter out diff files
    json_files = [f for f in json_files if not f.name.endswith('_diff.json')]
    
    logging.info(f"Found {len(json_files)} files to ingest")
    print(f"Found {len(json_files)} alert files")
    
    # Ingest each file
    total_docs = 0
    for idx, file_path in enumerate(json_files, 1):
        print(f"Processing [{idx}/{len(json_files)}]: {file_path.name}")
        count = ingest_file(file_path, db)
        total_docs += count
        print(f"  → Ingested {count} documents")
    
    # Print summary
    stats = db.get_collection_stats()
    print("\n" + "="*80)
    print("Ingestion Complete")
    print("="*80)
    print(f"Total files processed: {len(json_files)}")
    print(f"Total documents ingested: {total_docs}")
    print(f"Collection stats: {stats['document_count']} documents in '{stats['collection_name']}'")
    print("="*80)
    
    logging.info(f"Ingestion complete: {total_docs} documents from {len(json_files)} files")


def main():
    """Run ingestion on cleaned data folder."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Ingest PBS WARN alerts into Chroma vector database"
    )
    parser.add_argument(
        '--input-folder',
        default=DEFAULT_INPUT_FOLDER,
        help='Folder containing alert JSON files'
    )
    parser.add_argument(
        '--chroma-path',
        default=DEFAULT_CHROMA_PATH,
        help='Path to Chroma database'
    )
    parser.add_argument(
        '--file-pattern',
        default='pbs_warn_alerts_*.json',
        help='Glob pattern for JSON files'
    )
    
    args = parser.parse_args()
    
    try:
        ingest_folder(
            input_folder=args.input_folder,
            chroma_path=args.chroma_path,
            file_pattern=args.file_pattern
        )
    except Exception as e:
        logging.error(f"Error in main: {e}")
        print(f"Error: {e}")
        raise


if __name__ == "__main__":
    main()