


from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt
from bson import json_util, ObjectId
from .. import mongo
from ..routes_schema_utility import get_user_details, get_user_context_details, get_user_feed_details, get_portfolio_details, get_project_feed_details, convert_objectid_to_str
import json
import requests
import os
from dotenv import load_dotenv
import json
import requests


# Load environment variables from .env file
load_dotenv()

VSresume_autofill_bp = Blueprint('VSresume_autofill_bp', __name__)

@VSresume_autofill_bp.route('/VSresume_autofill', methods=['POST'])

def VSresume_autofill():

    data = request.json
    extracted_text =  data.get('extracted_text')
    api_key = os.getenv("VECTORSHIFT_API_KEY")

    if not api_key:
        return jsonify({"error": "API key not found in environment variables"}), 500

    if not extracted_text:
        return jsonify({"error": "No extracted text provided"}), 400
    
    
    url = "https://api.vectorshift.ai/api/pipelines/run"

    headers = {
        "Api-Key": api_key,
    }

    data = {
        # String inputs, or JSON representations of files for File inputs
        "inputs": json.dumps({
            "Links_extractor": "Extract all professional and social media links from the resume, including LinkedIn, GitHub, personal websites, and other relevant online profiles.",
            "GradYr_extractor": "Identify and extract the graduation year or expected graduation year from the education section of the resume. If multiple years are present, prioritize the most recent or future date.",
            "Skill_extractor": "Compile a comprehensive list of all professional skills, technical competencies, and relevant abilities mentioned throughout the resume. Include both hard and soft skills.",
            "LastSchool_extractor": "Identify and extract the name of the most recent educational institution attended by the applicant, as listed in the education section of the resume.",
            "Generate_biography": "Create a concise professional biography of the applicant based on the information provided in the resume. Include key achievements, work experience, educational background, and notable skills. The biography should be approximately 5-7 sentences long.",
            "Interest_extractor": "Identify and list any personal interests, hobbies, or extracurricular activities mentioned in the resume. If not explicitly stated, infer potential interests based on volunteer work, projects, or other relevant information.",
            "Major_extractor": "Extract the applicant's major or field of study from the most recent educational entry in the resume. If multiple fields of study are listed, include all of them."
    }),
        "pipeline_name": "Pipe Resume",
        "username": "bykho",
    }

    response = requests.post(url, headers=headers, data=data, files=extracted_text)
    response = response.json()
