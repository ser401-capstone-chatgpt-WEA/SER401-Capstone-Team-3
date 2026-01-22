"""Test script to verify RAG ingestion."""

from chroma_setup import ChromaDBManager

def main():
    db = ChromaDBManager()
    
    # Print stats
    stats = db.get_collection_stats()
    print("\n" + "="*80)
    print("RAG Database Status")
    print("="*80)
    print(f"Documents indexed: {stats['document_count']}")
    print(f"Collection: {stats['collection_name']}")
    print("="*80)
    
    # Test query
    print("\nTesting semantic search...")
    results = db.query(
        query_texts=["severe weather warning"],
        n_results=3
    )
    
    print(f"\nTop {len(results['ids'][0])} results for 'severe weather warning':")
    for i, (doc_id, doc, meta, dist) in enumerate(zip(
        results['ids'][0],
        results['documents'][0],
        results['metadatas'][0],
        results['distances'][0]
    ), 1):
        print(f"\n[{i}] Distance: {dist:.4f}")
        print(f"    Event: {meta.get('event')}")
        print(f"    Sent: {meta.get('sent')}")
        print(f"    Expires: {meta.get('expires')}")
        print(f"    Severity: {meta.get('severity')}")
        print(f"    Sender: {meta.get('sender')}")
        print(f"    Text: {doc[:200]}...")

if __name__ == "__main__":
    main()