import os
import openai
import pinecone
from pymongo import MongoClient
from tqdm import tqdm
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()

# OpenAI API key
openai.api_key = os.environ.get('OPENAI_API_KEY')

# Initialize Pinecone
pinecone.init(
    api_key=os.environ.get('PINECONE_API_KEY'),
    environment=os.environ.get('PINECONE_ENVIRONMENT')
)
index_name = os.environ.get('PINECONE_INDEX_NAME')
index = pinecone.Index(index_name)

# MongoDB connection setup
MONGO_URI = os.environ.get('MONGO_URI')
mongo_client = MongoClient(MONGO_URI)
db = mongo_client['arxiv_database']
collection = db['arxiv_collection']

def generate_embeddings_and_upload():
    batch_size = 100  # Adjust based on rate limits and performance
    cursor = collection.find({}, {'title': 1, 'abstract': 1, 'arxiv_id': 1})
    total_documents = collection.count_documents({})

    batch_texts = []
    batch_ids = []
    batch_metadata = []

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
                # Include additional metadata if needed
            })

            # Process the batch when it's full
            if len(batch_texts) >= batch_size:
                process_batch(batch_ids, batch_texts, batch_metadata)
                batch_texts.clear()
                batch_ids.clear()
                batch_metadata.clear()

        except Exception as e:
            print(f'Error processing document {document.get("_id")}: {e}')

    # Process any remaining items in the batch
    if batch_texts:
        process_batch(batch_ids, batch_texts, batch_metadata)

def process_batch(batch_ids, batch_texts, batch_metadata):
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
            success = True  # If upsert succeeds, exit the loop

        except openai.error.RateLimitError as e:
            print(f'OpenAI RateLimitError: {e}')
            retry_count += 1
            print(f'Retrying after {sleep_time} seconds...')
            time.sleep(sleep_time)
            sleep_time *= 2  # Exponential backoff

        except pinecone.core.client.exceptions.ApiException as e:
            print(f'Pinecone ApiException: {e}')
            retry_count += 1
            print(f'Retrying after {sleep_time} seconds...')
            time.sleep(sleep_time)
            sleep_time *= 2

        except Exception as e:
            print(f'Error in process_batch: {e}')
            break  # Exit on unknown exceptions

    if not success:
        print('Failed to process batch after multiple retries.')

if __name__ == '__main__':
    generate_embeddings_and_upload()
    print('Embedding generation and upload completed.')
