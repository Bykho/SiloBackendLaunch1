import os
from pinecone import Pinecone, ServerlessSpec
import openai
from dotenv import load_dotenv

load_dotenv()

pc = Pinecone(api_key=os.getenv("PINECONE_KEY"))
openai.api_key = os.getenv("OPENAI_API_KEY")

INDEX_NAME = "user-feed-index"
DIMENSION = 1536  # Dimension for text-embedding-ada-002

def initialize_pinecone():
    if INDEX_NAME not in pc.list_indexes().names():
        pc.create_index(
            name=INDEX_NAME,
            dimension=DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )
    return pc.Index(INDEX_NAME)

def get_embedding(text):
    response = openai.Embedding.create(
        input=text,
        model="text-embedding-ada-002"
    )
    return response['data'][0]['embedding']

def upsert_vector(index, id, vector, metadata=None):
    index.upsert(vectors=[(id, vector, metadata)])

def query_similar_vectors(index, vector, top_k=5):
    results = index.query(vector=vector, top_k=top_k, include_metadata=True)
    return results['matches']