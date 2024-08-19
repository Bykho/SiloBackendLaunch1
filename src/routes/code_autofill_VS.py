


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

VS_code_autofill_bp = Blueprint('VS_code_autofill_bp', __name__)

@VS_code_autofill_bp.route('/VS_code_autofill_bp', methods=['POST'])
def code_autofill_VS_bp():
    data = request.json
    extracted_text =  data.get('extracted_text')
    api_key = os.getenv("VECTORSHIFT_API_KEY")
    if not api_key:
        return jsonify({"error": "API key not found in environment variables"}), 500

    if not extracted_text:
        return jsonify({"error": "No extracted text provided"}), 400
    
    temp_file_path = "/tmp/combined_data.txt"
    with open(temp_file_path, 'w') as temp_file:
        temp_file.write(extracted_text)
    
    url = "https://api.vectorshift.ai/api/pipelines/run"
 
    files = {
        "Document": open(temp_file_path, 'rb')
    }

    headers = {
        "Api-Key": "YOUR_API_KEY",
    }

    data = {
        # String inputs, or JSON representations of files for File inputs
        "inputs": json.dumps({
            "input_2": "Provide a high-level summary of the entire codebase. Focus on the overall functionality, purpose, and main components of the project. Describe the project's goals, the problem it solves, and how the code is structured to achieve these goals.",
            "input_3": "Break down the specific methods and approaches used in the code. This should include explanations of the algorithms, design patterns, or architectural decisions that were implemented. Discuss how these methods contribute to the overall functionality and efficiency of the project.",
            "input_5": "Summarize the different layers or modules within the code. Each section should cover a different aspect, such as the abstract, results, future work, and any additional topics relevant to the codebase. This will help in understanding how the code is divided into different functional areas.",
            "input_1": "Generate a concise project name and a list of relevant tags that categorize the project's domain. The tags should reflect the key topics the code addresses, such as 'machine learning', 'computer vision', 'NLP', etc.",
            "input_4": "Identify potential areas of improvement or expansion for the project. This section should highlight any limitations of the current implementation and suggest future enhancements or directions that could be taken to build upon the existing code.",
    }),
        "pipeline_name": "Code Pipe",
        "username": "bykho",
    }

    response = requests.post(url, headers=headers, data=data, files=files)
    response = response.json()

            
