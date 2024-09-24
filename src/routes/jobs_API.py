

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from .. import mongo
from datetime import datetime, timedelta
from bson import ObjectId
import requests
import os
from .pinecone_utils import *
from datetime import datetime, timedelta

jobs_bp = Blueprint('jobs', __name__)
pinecone_index = initialize_pinecone()


end_date = datetime.now().date()
start_date = end_date - timedelta(days=30)  # Starting 30 days ago
# Ensure the start_date is at least two days before the current date for the API to collect all jobs
if (end_date - start_date).days < 2:
    start_date = end_date - timedelta(days=2)


@jobs_bp.route('/search_jobs', methods=['GET'])
@jwt_required()
def search_jobs():
    print('opened route')
    api_key = os.getenv("RAPIDAPI_KEY")
    url = "https://daily-international-job-postings.p.rapidapi.com/api/v2/jobs/search"
    params = {
        "countryCode": "US",
        "title": "+Engineer,+Developer",
        "dateCreated": "2024-09",
        "page": 1,
        "industry": "engineering,software,research", 
        "skills": "Python,Java,C++",
    }
    headers = {
        "x-rapidapi-host": "daily-international-job-postings.p.rapidapi.com",
        "x-rapidapi-key": api_key
    }
    try:
        last_fetch = mongo.db.theirstack_metadata.find_one({"_id": "last_fetch"})
        last_fetch = None 
        if last_fetch is None or datetime.utcnow() - last_fetch['timestamp'] > timedelta(hours=24):
            
            clear_job_vectors(pinecone_index)
            
            print("Fetching new data from API")
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            jobs_data = response.json().get('result', [])
            #print(f"API Response: {response.json()}")  # Print entire API response
            print(f"Number of jobs fetched: {len(jobs_data)}")
            if jobs_data:
                print("Clearing existing data in MongoDB")
                mongo.db.theirstack_daily_jobs.delete_many({})
                print("Formatting and inserting new job data")
                formatted_jobs = []
                print(f"response length: ", len(jobs_data))
                for job in jobs_data:
                    formatted_job = {
                        '_id': ObjectId(),
                        'title': job.get('title', 'No Title'),
                        'company': job.get('company', 'No Company'),
                        'location': f"{job.get('city', '')}, {job.get('state', '')}",
                        'country': job.get('countryCode', 'N/A'),
                        'description': job.get('jsonLD', {}).get('description', 'No Description'),
                        'date_posted': job.get('dateCreated', 'N/A'),
                        'url': job.get('jsonLD', {}).get('url', 'N/A'),
                        'skills': job.get('skills', []),  # Default to an empty list if 'skills' is missing
                        'industry': job.get('industry', 'N/A'),
                        'work_type': job.get('workType', ['N/A'])[0],
                        'contract_type': job.get('contractType', ['N/A'])[0],
                        'timezone': job.get('timezone', 'N/A'),
                        'occupation': job.get('occupation', 'N/A'),
                        'language': job.get('language', 'N/A'),
                        'source': job.get('source', 'N/A'),
                        'jsonLD': job.get('jsonLD', {})
                    }
                    formatted_jobs.append(formatted_job)
                #print("formatted Jobs, ", formatted_jobs)
                mongo.db.theirstack_daily_jobs.insert_many(formatted_jobs)
                update_job_embeddings(formatted_jobs)
            # Update last fetch time
            mongo.db.theirstack_metadata.update_one(
                {"_id": "last_fetch"},
                {"$set": {"timestamp": datetime.utcnow()}},
                upsert=True
            )
            print(f"Updated jobs data. {len(jobs_data)} jobs fetched.")
        else:
            print("Jobs data is up to date. Fetching from MongoDB.")
        # Get user embedding (you might want to pass user_id as a parameter)
        jwt_claims = get_jwt()
        print('\n \n \n here are jwt_claims: ', jwt_claims)
        user_id = jwt_claims.get('_id')
        user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            return jsonify({"error": "User not found"}), 404
        user_embedding = get_or_create_user_embedding(pinecone_index, user)
        # Query Pinecone for similar job vectors
        similar_jobs = query_similar_vectors_jobs(pinecone_index, user_embedding, top_k=5)
        # Get job IDs in order of similarity
        job_ids = [match['id'] for match in similar_jobs]

        print('\n \n \n here are job_ids: ', job_ids)
        # Fetch jobs from MongoDB in the order of similarity
        jobs_list = []
        for job_id in job_ids:
            job = mongo.db.theirstack_daily_jobs.find_one({"_id": ObjectId(job_id)})
            if job:
                job['_id'] = str(job['_id'])
                job['location'] = job.get('location') or "Location Not Listed"
                jobs_list.append(job)

        return jsonify(jobs_list), 200
    except Exception as e:
        print(f"Error in search_jobs: {str(e)}")
        print(f"Error occurred while processing job data")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "An unexpected error occurred while processing job data"}), 500
    
def update_job_embeddings(jobs_data):
    for job in jobs_data:
        try:
            job_content = f"{job['title']} {job['jsonLD'].get('description', '')} {job['company']}"
            job_embedding = get_embedding(job_content)
            print(f"Generated embedding for job ID: {job['_id']}")
            upsert_vector(pinecone_index, str(job['_id']), job_embedding, metadata={"type": "job", "job_id": str(job['_id'])})
            print(f"Upserted job ID {job['_id']} to Pinecone")
        except Exception as e:
            print(f"Error updating embedding for job ID {job['_id']}: {str(e)}")
    print(f"Updated embeddings for {len(jobs_data)} jobs")
