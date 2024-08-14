


from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import json_util, ObjectId
from .. import mongo
from ..routes_schema_utility import get_user_details, get_user_context_details, get_user_feed_details, get_portfolio_details, get_project_feed_details, convert_objectid_to_str
import json
import requests
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

VSscores_bp = Blueprint('VSscores_bp', __name__)

@VSscores_bp.route('/VSprofileScore', methods=['POST'])
@jwt_required()
def VSprofileScore():
    print('\n \n \n')
    print('made it into VSprofileScore')
    try:

        api_key = os.getenv("VECTORSHIFT_API_KEY")
        if not api_key:
            return jsonify({"error": "API key not found in environment variables"}), 500

        data = request.json
        combined_text = ""
        for key, value in data.items():
            combined_text += f"{key}: {value}\n"
        print('Here is combined text: \n ', combined_text)
        temp_file_path = "/tmp/combined_data.txt"
        with open(temp_file_path, 'w') as temp_file:
            temp_file.write(combined_text)

        # Prepare the Vectorshift API request
        url = "https://api.vectorshift.ai/api/pipelines/run"
        headers = {
            "Api-Key": api_key,
        }
        files = {
            "Document": open(temp_file_path, 'rb')
        }
        data = {
            "inputs": json.dumps({
                "Task1": "Please score this text from 0 to 100 in terms of how theoretically focused this work is. When considering the score 1-100 consider 100 as the top theoretical expert in this field -- be critical or even harsh and favor lower scores. Only give a number 1-100, no extra text. The response key for this should be 'Theory'",
                "Task2": "Please score this text from 0 to 100 in terms of the level of technical depth (taht is to say, the extent to which it demonstrates full technical knowledge) in this work. When considering the score 1-100 consider 100 as the top technical expert in this field -- be critical or even harsh and favor lower scores. Only give a number 1-100, no extra text. The response key for this should be 'Technical Depth'",
                "Task3": "Please score this text from 0 to 100 in terms of how practically focused this work is. When considering the score 1-100 consider 100 as the most practiced expert in this field -- be critical or even harsh and favor lower scores. Only give a number 1-100, no extra text. The response key for this should be 'Practicum'",
                "Task4": "Please score this text from 0 to 100 in terms of how collaborative this work is. When considering the score 1-100 consider 100 as the most collaborative project of all time, 0 a solo project -- be critical or even harsh. Only give a number 1-100, no extra text. The response key for this should be 'Collaboration'",
                "Task5": "Please score this text from 0 to 100 in terms of how entrepeneurially focused this work is. When considering the score 1-100 consider 100 as the most entrepeneurial person ever, 0 to be a person who is most likely an employee -- be critical or even harsh. Only give a number 1-100, no extra text. The response key for this should be 'Entrepreneurship'",
                "Document": combined_text
            }),
            "pipeline_name": "Document task completion agent Template",
            "username": "bykho",
        }

        # Send the request to Vectorshift
        response = requests.post(url, headers=headers, data=data, files=files)
        response_data = response.json()
        print('here is the response_data: \n', response_data)
        print('here is response_data type: ', type(response_data))

        # Extract the nested JSON string from 'output_1' and convert it to a dictionary
        output_dict = json.loads(response_data['output_1'])

        # Create a dictionary with the 'theoretical', 'technical', and 'practical' keys and their corresponding values
        score_dict = {
            'Theory': output_dict.get('Theory'),
            'Technical Depth': output_dict.get('Technical Depth'),
            'Practicum': output_dict.get('Practicum'),
            'Collaboration': output_dict.get('Collaboration'),
            'Entrepreneurship': output_dict.get('Entrepreneurship')
        }

        # Print the created dictionary to verify
        print('Extracted scores: \n', score_dict)
  
        # Clean up the temporary file
        os.remove(temp_file_path)

        # Return the response from Vectorshift
        return jsonify(score_dict), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # Ensure the file is closed
        if 'files' in locals():
            files['Document'].close()