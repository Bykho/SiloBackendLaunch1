from pymongo import MongoClient
from bson import ObjectId
import os
from pinecone import Pinecone
from routes.pinecone_utils import get_embedding, upsert_vector, delete_vector

# Initialize MongoDB client
mongo_client = MongoClient("mongodb+srv://nico:PleaseWork!@cluster0.iyzohjf.mongodb.net/ProductionDatabase?retryWrites=true&w=majority&ssl=true&tlsAllowInvalidCertificates=true")
mongo_db = mongo_client["ProductionDatabase"]
projects_collection = mongo_db.projects

# Initialize Pinecone client
pinecone_client = Pinecone(api_key="ca1e81e0-7ce9-4037-a619-aea036b0d78f")
pinecone_index = pinecone_client.Index("silo-production")

# Fetch all job IDs from MongoDB
job_ids = mongo_db.theirstack_daily_jobs.find({}, {"_id": 1})
job_ids = [str(job["_id"]) for job in job_ids]

# Check if the job IDs exist in Pinecone
pinecone_results = pinecone_index.fetch(ids=job_ids)

# Print the results
existing_count = 0
for job_id in job_ids:
    if job_id in pinecone_results.get("vectors", {}):
        print(f"Job ID {job_id} exists in Pinecone.")
        existing_count += 1
    else:
        print(f"Job ID {job_id} does not exist in Pinecone.")

# Print the number of job IDs that exist in Pinecone
print(f"Number of job IDs that exist in Pinecone: {existing_count}")

def delete_jobs_from_pinecone():
    job_ids = mongo_db.theirstack_daily_jobs.find({}, {"_id": 1})
    job_ids = [str(job["_id"]) for job in job_ids]
    delete_vector(pinecone_index, job_ids)
    print(f"Deleted {len(job_ids)} job IDs from Pinecone.")

def reembed_jobs_to_pinecone():
    jobs_data = mongo_db.theirstack_daily_jobs.find({})
    counter = 0
    for job in jobs_data:
        job_content = f"{job['job_title']} {job['description']} {job['company']}"
        job_embedding = get_embedding(job_content)
        upsert_vector(pinecone_index, str(job['_id']), job_embedding, metadata={"type": "job", "job_id": str(job['_id'])})
        counter += 1
        if counter % 10 == 0:  # Print progress every 10 jobs
            print(f"Processed {counter} jobs...")
    print(f"Re-embedded {counter} jobs to Pinecone.")


import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--delete":
        print("Starting deletion of jobs from Pinecone...")
        delete_jobs_from_pinecone()
        print("Deletion complete!")
    if len(sys.argv) > 1 and sys.argv[1] == "--reembed":
        print("Starting re-embedding of jobs to Pinecone...")
        reembed_jobs_to_pinecone()
        print("Re-embedding complete!")