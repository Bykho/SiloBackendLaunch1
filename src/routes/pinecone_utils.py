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

def clear_job_vectors(index):
    try:
        batch_size = 1000  # Maximum number of IDs we can delete at once
        total_deleted = 0

        while True:
            # Fetch a batch of job vectors
            fetch_response = index.query(
                vector=[0] * DIMENSION,  # dummy vector
                filter={"type": "job"},
                top_k=batch_size,
                include_metadata=True
            )
            
            job_ids = [match['id'] for match in fetch_response['matches']]
            
            if not job_ids:
                break  # No more job vectors to delete
            
            # Delete the batch of job vectors
            index.delete(ids=job_ids)
            total_deleted += len(job_ids)
            
            print(f"Deleted batch of {len(job_ids)} job vectors")
            
            if len(job_ids) < batch_size:
                break  # We've deleted all job vectors

        print(f"Total job vectors cleared from Pinecone index: {total_deleted}")
    except Exception as e:
        print(f"Error clearing job vectors from Pinecone: {str(e)}")

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