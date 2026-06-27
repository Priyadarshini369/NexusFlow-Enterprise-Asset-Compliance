import os
import time
import chromadb
from chromadb.config import Settings

def seed_database():
    print("🌱 Initializing ChromaDB Seed Script...")
    
    chroma_host = os.environ.get("CHROMA_HOST", "nexusflow-vectors")
    chroma_port = os.environ.get("CHROMA_PORT", "8000")
    
    client = None
    for attempt in range(5):
        try:
            print(f"📡 Connecting to ChromaDB container at {chroma_host}:{chroma_port} (Attempt {attempt + 1}/5)...")
            
            # Explicitly configure settings to enforce compatibility with modern Chroma servers
            client = chromadb.HttpClient(
                host=chroma_host, 
                port=int(chroma_port),
                settings=Settings(
                    chroma_api_impl="chromadb.api.fastapi.FastAPI",
                    persist_directory=None
                )
            )
            client.heartbeat()
            break
        except Exception as e:
            if attempt < 4:
                print(f"⏳ Waiting for vector server routing layer... ({str(e)[:60]})")
                time.sleep(2)
            else:
                print("❌ Max retries reached. Container connection timed out.")
                raise e

    # Access or generate the correct compliance policy block
    collection = client.get_or_create_collection(name="nexusflow_business_policies")
    
    # Seed corporate policy data
    policies = [
        "NEXUSFLOW RISK THRESHOLD POLICY: Any luxury asset, jewelry, or precious metal exceeding a market valuation of $10,000 USD is classified as a Tier-1 High-Value Risk Asset. Tier-1 assets require secondary physical authentication.",
        "NEXUSFLOW BRAND COMPLIANCE: Items matching the Cartier Panthère collection must be verified against the official product catalog to prevent counterfeit asset ingestion into client portfolios."
    ]
    
    collection.add(
        documents=policies,
        ids=["policy_001", "policy_002"]
    )
    print("✅ ChromaDB seeded successfully with corporate compliance guidelines!")

if __name__ == "__main__":
    seed_database()