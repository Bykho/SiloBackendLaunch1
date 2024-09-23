

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

load_dotenv()

jobs_bp = Blueprint('jobs', __name__)
pinecone_index = initialize_pinecone()


@jobs_bp.route('/search_jobs', methods=['GET'])
@jwt_required()
def search_jobs():
    print('opened route')
    api_key = os.getenv("THEIRSTACK_KEY")

    #switch to Post request w/ sending data.

    url = "https://api.theirstack.com/v1/jobs/search"

    
    payload = {
        "order_by": [
            {
                "desc": True,
                "field": "date_posted"
            },
            {
                "desc": True,
                "field": "discovered_at"
            }
        ],
        "page": 0,
        "limit": 5000,
        "company_description_pattern_or": [],
        "company_description_pattern_not": [],
        "company_description_pattern_accent_insensitive": False,
        "min_revenue_usd": 5000000,
        "max_revenue_usd": None,
        "min_employee_count": 10,
        "max_employee_count": None,
        "min_employee_count_or_null": None,
        "max_employee_count_or_null": None,
        "min_funding_usd": None,
        "max_funding_usd": None,
        "funding_stage_or": [],
        "industry_or": [], 
        "industry_not": [],
        "industry_id_or": [1,4,53, 3127, 1285, 113, 2458, 383, 119, 1649, 1644, 8, 94, 87, 95, 3242, 3248, 118, 3102, 12, 114, 7, 147, 3247, 3251, 3, 52 ],
        "industry_id_not": [],
        "company_tags_or": [],
        "company_type": "all",
        "company_investors_or": [],
        "company_investors_partial_match_or": [],
        "company_technology_slug_or": [],
        "company_technology_slug_and": [],
        "company_technology_slug_not": [],
        "only_yc_companies": False,
        "company_location_pattern_or": [],
        "company_country_code_or": ["US"],
        "company_country_code_not": [],
        "company_list_id_or": [],
        "company_list_id_not": [],
        "company_linkedin_url_exists": None,
        "revealed_company_data": None,
        "company_name_or": [],
        "company_name_case_insensitive_or": [],
        "company_id_or": [],
        "company_domain_or": [],
        "company_domain_not": [],
        "company_name_not": ["Davidayo"],
        "company_name_partial_match_or": [],
        "company_name_partial_match_not": [],
        "company_linkedin_url_or": [],
        "job_title_or": [],
        "job_title_not": [],
        "job_title_pattern_and": [],
        "job_title_pattern_or": [],
        "job_title_pattern_not": ["consultant","support","administrator", "administrative", "business", "finance", "barber", "stylist", "artist", "executive", "HR", "Chairman", "Recruiting", "Recruiter", "Resources", "Administrator", "Security", "Assistant", "Concierge", "Secretary", "Janitor", "Sanitation", "Host", "Hostess", "Service","Technician", "Tech", "Writer", "Grant", "Physician", "Nurse", "Senior", "Sr.", "Director", "Principal", "Co-op", "Contract"],
        "job_country_code_or": ["US"],
        "job_country_code_not": [],
        "posted_at_max_age_days": None,
        "posted_at_gte": None,
        "posted_at_lte": None,
        "discovered_at_max_age_days": 31,
        "discovered_at_min_age_days": None,
        "discovered_at_gte": None,
        "discovered_at_lte": None,
        "job_description_pattern_or": ["engineer", "engineering", "STEM", "scientist", "research", "mechanical", "robotics", "aerospace"],
        "job_description_pattern_not": ["marketing","sales", "finance","accounting","HR" ,"copywriter", "legal", "lawyer","attorney","administrative","business","teacher", "instructor", "nurse", "doctor", "physician", "chef","consulting", "consulting"],
        "job_description_pattern_is_case_insensitive": True,
        "remote": None,
        "only_jobs_with_reports_to": None,
        "reports_to_exists": None,
        "final_url_exists": None,
        "only_jobs_with_hiring_managers": None,
        "hiring_managers_exists": None,
        "job_id_or": [],
        "job_ids": [],
        "min_salary_usd": None,
        "max_salary_usd": None,
        "job_technology_slug_or": [],
        "job_technology_slug_not": [],
        "job_technology_slug_and": [],
        "job_location_pattern_or": [],
        "job_location_pattern_not": [],
        "scraper_name_pattern_or": [],
        "include_total_results": False,
        "blur_company_data": False,
        "group_by": []
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"  # Replace with your actual API key
    }

    try:
        last_fetch = mongo.db.theirstack_metadata.find_one({"_id": "last_fetch"})
        
        if last_fetch is None or datetime.utcnow() - last_fetch['timestamp'] > timedelta(hours=24):
        #if True: #for testing
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            
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