import os
import openai
from pymongo import MongoClient
from tqdm import tqdm
from dotenv import load_dotenv
import time
from pinecone import Pinecone, ServerlessSpec

# Load environment variables
load_dotenv()

# OpenAI API key
openai.api_key = os.environ.get('OPENAI_API_KEY')

# Initialize Pinecone
pc = Pinecone(api_key=os.getenv("PINECONE_KEY"))
index_name = 'silo-production'  # Using the "silo-production" index
index = pc.Index(index_name)

print(f"Index {index_name} initialized.")

# MongoDB connection setup
MONGO_URI = os.environ.get('MONGO_URI')
mongo_client = MongoClient(MONGO_URI)
db = mongo_client['arxiv_database']
collection = db['arxiv_collection']
print("MongoDB connection established.")

def generate_embeddings_and_upload():
    count = 0
    batch_size = 100  # Adjust based on rate limits and performance
    cursor = collection.find(
        {
            'embedding_processed': {'$ne': True},  # Process only unprocessed documents
            'journal_ref': {'$ne': None}  # Ensure journal_ref is not null
        },
        {'title': 1, 'abstract': 1, 'arxiv_id': 1}
    )
    total_documents = collection.count_documents({
        'embedding_processed': {'$ne': True},
        'journal_ref': {'$ne': None}
    })

    batch_texts = []
    batch_ids = []
    batch_metadata = []
    batch_mongo_ids = []

    for document in tqdm(cursor, total=total_documents, desc='Processing documents'):
        try:
            arxiv_id = document.get('arxiv_id')
            mongo_id = str(document.get('_id'))
            title = document.get('title', '')
            abstract = document.get('abstract', '')
            text_to_embed = f"{title}\n\n{abstract}"

            batch_texts.append(text_to_embed)
            batch_ids.append(mongo_id)
            batch_metadata.append({
                'arxiv_id': arxiv_id,
                'mongo_id': mongo_id,
                'title': title,
                'type': 'research'  # Adding metadata type: research
                # Include additional metadata if needed
            })
            batch_mongo_ids.append(document['_id'])
            count += 1
            # Process the batch when it's full
            if len(batch_texts) >= batch_size:
                process_batch(batch_ids, batch_texts, batch_metadata, batch_mongo_ids)
                print(f'Batch processed. Batch size: {batch_size}')
                batch_texts.clear()
                batch_ids.clear()
                batch_metadata.clear()
                batch_mongo_ids.clear()

        except Exception as e:
            print(f'Error processing document {document.get("_id")}: {e}')

    # Process any remaining items in the batch
    if batch_texts:
        process_batch(batch_ids, batch_texts, batch_metadata, batch_mongo_ids)
        batch_texts.clear()
        batch_ids.clear()
        batch_metadata.clear()
        batch_mongo_ids.clear()

def process_batch(batch_ids, batch_texts, batch_metadata, batch_mongo_ids):
    success = False
    retry_count = 0
    max_retries = 5
    sleep_time = 60  # Initial sleep time in seconds

    while not success and retry_count < max_retries:
        try:
            # Generate embeddings
            response = openai.Embedding.create(
                input=batch_texts,
                model='text-embedding-ada-002'
            )
            embeddings = [record['embedding'] for record in response['data']]

            # Prepare data for Pinecone upsert
            vectors = []
            for idx, embedding in enumerate(embeddings):
                vector = {
                    'id': batch_ids[idx],
                    'values': embedding,
                    'metadata': batch_metadata[idx]
                }
                vectors.append(vector)

            # Upsert to Pinecone
            index.upsert(vectors)

            # Update MongoDB to mark documents as processed
            collection.update_many(
                {'_id': {'$in': batch_mongo_ids}},
                {'$set': {'embedding_processed': True}}
            )

            success = True  # If upsert succeeds, exit the loop

        except openai.error.RateLimitError as e:
            print(f'OpenAI RateLimitError: {e}')
            retry_count += 1
            print(f'Retrying after {sleep_time} seconds...')
            time.sleep(sleep_time)
            sleep_time *= 2  # Exponential backoff

        except Exception as e:
            print(f'Error in process_batch: {e}')
            retry_count += 1
            print(f'Retrying after {sleep_time} seconds...')
            time.sleep(sleep_time)
            sleep_time *= 2

    if not success:
        print('Failed to process batch after multiple retries.')

if __name__ == '__main__':
    generate_embeddings_and_upload()
    print('Embedding generation and upload completed.')