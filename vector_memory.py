import os
import chromadb

def get_vector_client():
    """
    Connects to the dedicated ChromaDB vector container 
    using the exact service name defined in docker-compose.
    """
    # Using the exact service name 'nexusflow-vectors' allows
    # the app container to find Chroma on the mesh network.
    chroma_host = os.environ.get("CHROMA_HOST", "nexusflow-vectors")
    chroma_port = os.environ.get("CHROMA_PORT", "8000")
    
    return chromadb.HttpClient(
        host=chroma_host,
        port=int(chroma_port)
    )

def store_long_term_memory(session_id: str, text_content: str, memory_id: str):
    """
    Converts a text conversation string into a vector 
    and saves it inside ChromaDB for semantic search retrieval later.
    """
    try:
        client = get_vector_client()
        collection = client.get_or_create_collection(name="nexusflow_agent_memory")
        
        collection.add(
            documents=[text_content],
            metadatas=[{"session_id": session_id}],
            ids=[memory_id]
        )
        return True
    except Exception as e:
        print(f"❌ [Vector Storage Error]: {e}")
        return False

def query_semantic_memory(search_query: str, n_results: int = 1) -> str:
    """
    Day 12 Pipeline Fix: Query the corporate knowledge database 
    and parse the output directly into structured text for Gemini.
    """
    try:
        client = get_vector_client()
        collection = client.get_or_create_collection(name="nexusflow_business_policies")
        
        results = collection.query(
            query_texts=[search_query],
            n_results=n_results
        )
        
        # Pull the clean text out of Chroma's raw structure
        if results and 'documents' in results and results['documents']:
            flat_docs = [doc for sublist in results['documents'] for doc in sublist]
            return "\n---\n".join(flat_docs)
            
        return "⚠️ No matching business rules found for this query context."
        
    except Exception as e:
        return f"⚠️ Could not pull corporate context out of ChromaDB: {str(e)}"