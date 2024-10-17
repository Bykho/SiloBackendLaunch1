import os
from pinecone import Pinecone, ServerlessSpec
import openai
from dotenv import load_dotenv

load_dotenv()

pc = Pinecone(api_key=os.getenv("PINECONE_KEY"))
openai.api_key = os.getenv("OPENAI_API_KEY")

INDEX_NAME = "silo-production"
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

def query_similar_vectors_research(pinecone_index, embedding, top_k=4):
    query_response = pinecone_index.query(
        vector=embedding,
        top_k=top_k,
        filter={"type": "research"},  # Filter based on metadata type
        include_values=False,
        include_metadata=True
    )
    return query_response['matches']


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

def query_similar_vectors_projects(index, vector, top_k=20):
    results = index.query(
        vector=vector,
        top_k=top_k,
        include_metadata=True,
        filter={"type": "project"}
    )
    return results['matches']

def query_similar_vectors_users(index, user_id, top_k=5):

    # Fetch the vector based on the user ID
    fetch_result = index.fetch(ids=[user_id])

    # Extract the vector from the result
    user_vector = fetch_result['vectors'][user_id]['values']

    results = index.query(
        vector = user_vector,
        top_k=top_k,
        include_metadata=True,
        filter={"type": "user"}
    )
    return results['matches']

def query_similar_vectors_jobs(index, vector, top_k=20):
    results = index.query(
        vector=vector,
        top_k=top_k,
        include_metadata=True,
        filter={"type": "job"}
    )
    return results['matches']


def get_or_create_user_embedding(index, user):
    user_id = str(user['_id'])
    
    # Check if user embedding exists in Pinecone
    result = index.fetch([user_id])
    
    if user_id in result['vectors']:
        # Embedding exists, return it
        return result['vectors'][user_id]['values']
    else:
        # Create new embedding
        user_profile = f"{user['biography']} {' '.join(user['skills'])} {' '.join(user['interests'])}"
        user_embedding = get_embedding(user_profile)
        
        # Upsert the new embedding
        upsert_vector(index, user_id, user_embedding, metadata={"type": "user", "username": user['username']})
        
        return user_embedding

