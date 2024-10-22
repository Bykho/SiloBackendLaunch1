

from flask import Blueprint, request, jsonify, send_from_directory
from flask import current_app as app
from flask_jwt_extended import jwt_required, get_jwt
from .. import mongo
from flask import Flask, jsonify
import requests
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
from bson import json_util, ObjectId
from ..routes_schema_utility import get_user_details, get_user_context_details, get_user_feed_details, get_portfolio_details, get_project_feed_details, convert_objectid_to_str
from .pinecone_utils import *
from ..routes.mixpanel_utils import track_event, set_user_profile
import datetime

load_dotenv()

jobs_bp = Blueprint('jobs', __name__)
pinecone_index = initialize_pinecone()


@jobs_bp.route('/search_jobs', methods=['GET'])
@jwt_required()
def search_jobs():
    print('opened jobs route')
    api_key = os.getenv("THEIRSTACK_KEY")

    #switch to Post request w/ sending data.
    #Industry IDs:
    # [1,4,53, 3127, 1285, 113, 2458, 383, 119, 1649, 1644, 8, 94, 87, 95, 3242, 3248, 118, 3102, 12, 114, 7, 147, 3247, 3251, 3, 52]
    url = "https://api.theirstack.com/v1/jobs/search"

    
    payload = {
    "page": 0,
    "limit": 500,
    "job_country_code_or": ["US"],
    "posted_at_max_age_days": 30,
    "only_yc_companies": True,
    "job_title_or": ["engineer", "engineering", "STEM", "scientist", "research", "mechanical", "robotics", "aerospace"]
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"  # Replace with your actual API key
    }

    try:

        jwt_claims = get_jwt()
        user_id = jwt_claims.get('_id')
    
        track_event(str(user_id), 'checked jobs', {'time': datetime.datetime.utcnow()})

        last_fetch = mongo.db.theirstack_metadata.find_one({"_id": "last_fetch"})
        
        #if last_fetch is None or datetime.utcnow() - last_fetch['timestamp'] > timedelta(hours=336):
        if True: #temporary
            print("Fetching new data from Theirstack API...")
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            print(response.json())
        
            jobs_data = response.json().get('data', [])
            
            if jobs_data:
                # Clear existing data
                mongo.db.theirstack_daily_jobs.delete_many({})
                
                # Insert new data
                mongo.db.theirstack_daily_jobs.insert_many(jobs_data)

                update_job_embeddings(jobs_data)
            
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
        user_id = jwt_claims.get('_id')

        user = mongo.db.users.find_one({"_id": ObjectId(user_id)})

        if not user:
            return jsonify({"error": "User not found"}), 404
        
        user_embedding = get_or_create_user_embedding(pinecone_index, user)

        # Query Pinecone for similar job vectors
        similar_jobs = query_similar_vectors_jobs(pinecone_index, user_embedding, top_k=500)

        # Get job IDs in order of similarity
        job_ids = [match['id'] for match in similar_jobs]
        
        # Fetch jobs from MongoDB in the order of similarity
        #print(f"Type of jobs_data: {type(jobs_data)}")
        #print(f"First item in jobs_data: {jobs_data[0] if jobs_data else 'Empty'}")
        
        jobs_list = []
        print(type(job_ids[1]))
        for job_id in job_ids:
            job = mongo.db.theirstack_daily_jobs.find_one({"_id": ObjectId(job_id)})
            if job:
                job['_id'] = str(job['_id'])
                if 'location' in job:
                    job['location'] = job['location']
                if job['location'] is None:
                    job['location'] = "Location Not Listed"
                jobs_list.append(job)
        
        return jsonify(jobs_list), 200

    except Exception as e:
        print(f"Error in search_jobs: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
def update_job_embeddings(jobs_data):
    for job in jobs_data:
        print("type", type(job))
        print("job", job)
        job_content = f"{job['job_title']} {job['description']} {job['company']}"
        job_embedding = get_embedding(job_content)
        upsert_vector(pinecone_index, str(job['_id']), job_embedding, metadata={"type": "job", "job_id": str(job['_id'])})
    print(f"Updated embeddings for {len(jobs_data)} jobs")

if __name__ == '__main__':
    app.run(debug=True)