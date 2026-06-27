import os
import requests
# Import standard embedding utility to populate vectors locally
from chromadb.utils import embedding_functions

def get_chroma_base_url():
    """
    Computes the backend direct HTTP router address using modern V2 space layouts.
    Changed default host fallback from 'chroma' to 'chromadb' to match the active container name.
    """
    chroma_host = os.environ.get("CHROMA_HOST", "chromadb")
    chroma_port = os.environ.get("CHROMA_PORT", "8000")
    return f"http://{chroma_host}:{chroma_port}/api/v2/tenants/default_tenant/databases/default_database"

def get_headers():
    """Returns standard JSON communication headers."""
    return {
        "Content-Type": "application/json"
    }

def ingest_policy_documents():
    """
    Day 9 Direct HTTP Pipeline: Generates embeddings locally and pushes
    them to the modern ChromaDB v2 multi-tenant server engine.
    """
    # Force background operation and suppress interactive download progress loops
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    
    base_url = get_chroma_base_url()
    headers = get_headers()
    collection_name = "nexusflow_business_policies"
    
    print(f"[Vector Store] Connecting directly via HTTP to V2 space: {base_url}")
    
    try:
        # 1. Fetch collections using the modern v2 tenant endpoint
        print(f"📡 Listing collections from {base_url}/collections...")
        list_resp = requests.get(f"{base_url}/collections", headers=headers)
        
        collection_id = None
        if list_resp.status_code == 200:
            collections = list_resp.json()
            for col in collections:
                if col.get("name") == collection_name:
                    collection_id = col.get("id")
                    print(f"🎯 Found existing collection. ID: {collection_id}")
                    break
        
        # 2. Create collection if it doesn't exist
        if not collection_id:
            print(f"✨ Creating collection under modern V2 spec: '{collection_name}'...")
            create_resp = requests.post(
                f"{base_url}/collections", 
                headers=headers,
                json={"name": collection_name}
            )
            
            if create_resp.status_code in [200, 201]:
                collection_id = create_resp.json()["id"]
                print(f"✅ Collection created successfully. ID: {collection_id}")
            else:
                print(f"❌ [Server Rejection] Status {create_resp.status_code}: {create_resp.text}")
                return

        # 3. Setup text documents
        kb_documents = [
            "POLICY-002: Damaged goods forensic clause. If an item arrives broken, the user must upload clear photographic evidence within 48 hours to trigger an automated fraud verification cycle.",
            "POLICY-003: High-value transactions exceeding $1,000 require manual compliance audit routing and supervisor confirmation before any refund protocol can execute.",
            "POLICY-004: LUXURY BRAND THRESHOLD: Any asset matching the Cartier Panthère collection must be scrutinized under extreme damage assessment limits to verify authenticity prior to asset verification."
        ]
        
        # 4. Generate text vectorizations locally so server validation passes
        print("🧠 Computing mathematical text vectors locally (Silent Background Mode)...")
        default_ef = embedding_functions.DefaultEmbeddingFunction()
        kb_embeddings = default_ef(kb_documents)

        # 5. Build strict modern payload containing vectors
        payload = {
            "documents": kb_documents,
            "embeddings": kb_embeddings,
            "metadatas": [
                {"category": "forensics", "doc_id": "DMG-48"},
                {"category": "compliance", "doc_id": "HIGH-VAL"},
                {"category": "luxury", "doc_id": "CARTIER-PANTH"}
            ],
            "ids": ["policy_002", "policy_003", "policy_004"]
        }
        
        # 6. Ingest vectorized payload into the database slot
        print(f"🚀 Pushing vectorized payload into collection target slot...")
        upsert_resp = requests.post(
            f"{base_url}/collections/{collection_id}/upsert", 
            headers=headers,
            json=payload
        )
        
        if upsert_resp.status_code in [200, 201, 204]:
            print("🎉 [Success] Day 9 Bulk Ingestion Complete! Network volume synchronized.")
        else:
            print(f"❌ Ingestion payload rejected with status {upsert_resp.status_code}: {upsert_resp.text}")
            
    except Exception as e:
        print(f"❌ [Network Error] Direct injection pipeline failed: {str(e)}")

def query_semantic_memory(search_query: str, n_results: int = 1) -> str:
    """
    Day 12 Direct Retrieval Bridge: Localizes query vectorizations to query the raw server layer.
    """
    # Force background operation and suppress interactive download progress loops
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    
    try:
        base_url = get_chroma_base_url()
        headers = get_headers()
        collection_name = "nexusflow_business_policies"
        
        list_resp = requests.get(f"{base_url}/collections", headers=headers)
        collection_id = None
        if list_resp.status_code == 200:
            for col in list_resp.json():
                if col.get("name") == collection_name:
                    collection_id = col.get("id")
                    break
        
        if not collection_id:
            return "⚠️ Corporate compliance collection does not exist in backend vector space."
        
        # Vectorize search string locally
        default_ef = embedding_functions.DefaultEmbeddingFunction()
        query_embeddings = default_ef([search_query])

        query_url = f"{base_url}/collections/{collection_id}/query"
        query_resp = requests.post(
            query_url, 
            headers=headers,
            json={"query_embeddings": query_embeddings, "n_results": n_results}
        )
        
        results = query_resp.json()
        if results and 'documents' in results and results['documents']:
            flat_docs = [doc for sublist in results['documents'] for doc in sublist]
            return "\n---\n".join(flat_docs)
            
        return "⚠️ No matching business rules found for this query context."
    except Exception as e:
        return f"⚠️ Could not pull corporate context out of ChromaDB: {str(e)}"

if __name__ == "__main__":
    ingest_policy_documents()