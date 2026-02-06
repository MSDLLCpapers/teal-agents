
import chromadb
CHROMA_PATH = "/app/chroma_agents"
COLLECTION_NAME = "agents_registry"

def get_collection():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_collection(COLLECTION_NAME)
