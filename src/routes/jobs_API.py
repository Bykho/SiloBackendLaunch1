

from flask import Blueprint, request, jsonify, send_from_directory
from flask import current_app as app
from flask_jwt_extended import jwt_required
from .. import mongo
from flask import Flask, jsonify
import requests
from dotenv import load_dotenv
import os



load_dotenv()

jobs_bp = Blueprint('jobs', __name__)

@jobs_bp.route('/search_jobs', methods=['GET'])
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
        "limit": 10,
        "company_description_pattern_or": [],
        "company_description_pattern_not": [],
        "company_description_pattern_accent_insensitive": False,
        "min_revenue_usd": None,
        "max_revenue_usd": None,
        "min_employee_count": None,
        "max_employee_count": None,
        "min_employee_count_or_null": None,
        "max_employee_count_or_null": None,
        "min_funding_usd": None,
        "max_funding_usd": None,
        "funding_stage_or": [],
        "industry_or": [],  # Filter by industry
        "industry_not": [],
        "industry_id_or": [],
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
        "company_country_code_or": [],
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
        "company_name_not": [],
        "company_name_partial_match_or": [],
        "company_name_partial_match_not": [],
        "company_linkedin_url_or": [],
        "job_title_or": [],
        "job_title_not": [],
        "job_title_pattern_and": [],
        "job_title_pattern_or": [],
        "job_title_pattern_not": [],
        "job_country_code_or": [],
        "job_country_code_not": [],
        "posted_at_max_age_days": None,
        "posted_at_gte": None,
        "posted_at_lte": None,
        "discovered_at_max_age_days": None,
        "discovered_at_min_age_days": None,
        "discovered_at_gte": None,
        "discovered_at_lte": None,
        "job_description_pattern_or": [],
        "job_description_pattern_not": [],
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
        "blur_company_data": True,
        "group_by": []
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"  # Replace with your actual API key
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()  # Raises an HTTPError for bad responses
        
        jobs_data = response.json().get('data', [])
        
        # Insert each job as a new entry in MongoDB
        if jobs_data:
            for job in jobs_data:
                mongo.db.theirstack_daily_jobs.insert_one(job)
        
        return jsonify({"message": "Jobs successfully saved to MongoDB", "saved_jobs": len(jobs_data)}), 200
    
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500


@jobs_bp.route('/get_jobs', methods=['GET'])
def get_jobs():
    try:
        jobs_cursor = mongo.db.theirstack_daily_jobs.find({}, {"id": 1, "company": 1, "cities": 1, "job_title": 1, "description": 1})
        
        jobs_list = list(jobs_cursor)
        
        for job in jobs_list:
            job['_id'] = str(job['_id'])
            
            # Handle the cities field
            if 'cities' in job and isinstance(job['cities'], list) and len(job['cities']) > 0:
                job['cities'] = job['cities'][0]
            else:
                job['cities'] = "no location found"
        
        print(f"jobs_list: {jobs_list}")
        return jsonify(jobs_list), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)