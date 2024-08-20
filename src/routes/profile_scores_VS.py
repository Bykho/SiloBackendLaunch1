


from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt
from bson import json_util, ObjectId
from .. import mongo
from ..routes_schema_utility import get_user_details, get_user_context_details, get_user_feed_details, get_portfolio_details, get_project_feed_details, convert_objectid_to_str
import json
import requests
import os
from dotenv import load_dotenv
from ..routes.mixpanel_utils import track_event

# Load environment variables from .env file
load_dotenv()

VSscores_bp = Blueprint('VSscores_bp', __name__)

@VSscores_bp.route('/VSprofileScore', methods=['POST'])
@jwt_required()
def VSprofileScore():
    print('\n \n \n')
    print('made it into VSprofileScore')
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')
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
                "Task1": "Please score this text from 0 to 100 in terms of how theoretically focused this work is. When considering the score 1-100 consider 100 as the top theoretical expert in this field -- be critical or even harsh and favor lower scores. As a reference, only a user on par with the greatest minds in science should get a 100, while a first year engineering student with very minimal experience should get close to 0. Only give a number 1-100, no extra text. The response key for this should be 'Theory'",
                "Task2": "Please score this text from 0 to 100 in terms of the level of technical depth (taht is to say, the extent to which it demonstrates full technical knowledge) in this work. When considering the score 1-100 consider 100 as the top technical expert in this field -- be critical or even harsh and favor lower scores. As a reference, only a user on par with the greatest minds in science should get a 100, while a first year engineering student with very minimal experience should get close to 0. Only give a number 1-100, no extra text. The response key for this should be 'TechnicalDepth'",
                "Task3": "Please score this text from 0 to 100 in terms of how practically focused this work is. When considering the score 1-100 consider 100 as the most practiced expert in this field -- be critical or even harsh and favor lower scores. Only give a number 1-100, no extra text. As a reference, only a user on par with the greatest minds in science should get a 100, while a first year engineering student with very minimal experience should get close to 0. The response key for this should be 'Practicum'",
                "Task4": "Please score this text from 0 to 100 in terms of how innovative/creative this work is. When considering the score 1-100 consider 100 as the most innovative/new/creative ideas of all time, at 0 we have someone that just recreates already created things -- be critical or even harsh. As a reference, only a user on par with the greatest minds in science should get a 100, while a first year engineering student with very minimal experience should get close to 0. Only give a number 1-100, no extra text. The response key for this should be 'Innovation'",
                "Task5": "Please score this text from 0 to 100 in terms of how much of a leader the person who made this work seems to be. When considering the score 1-100 consider 100 as the greatest leader of all time, 0 to be a person who is most likely an employee -- be critical or even harsh. As a reference, only a user on par with the greatest minds in science should get a 100, while a first year engineering student with very minimal experience should get close to 0. Only give a number 1-100, no extra text. The response key for this should be 'Leadership'",
                "Document": combined_text
            }),
            "pipeline_name": "Scores Pipe",
            "username": "bykho",
        }

        # Send the request to Vectorshift
        response = requests.post(url, headers=headers, data=data, files=files)
        response_data = response.json()
        print('here is the response_data: \n', response_data)
        print('here is response_data type: ', type(response_data))
        print('here is response_data[output_1]: ', response_data['output_1'])
        print('here is response_data[output_1] type: ', type(response_data['output_1']))

        # Extract the nested JSON string from 'output_1' and convert it to a dictionary
         # Fix the single quotes to double quotes in the JSON string
        json_output_str = response_data['output_1'].replace("'", "\"")
        #output_str = json_output_str.replace('\n', ', ')

        print('here is output_str: ', json_output_str)
        print('here is output_str type: ', type(json_output_str))
        # Extract the nested JSON string from 'output_1' and convert it to a dictionary
        output_dict = json.loads(json_output_str)

        print('here is the output_dict: ', output_dict)
        print('here is output_dict type: ', type(output_dict))
        # Create a dictionary with the 'theoretical', 'technical', and 'practical' keys and their corresponding values
        score_dict = {
            'Theory': output_dict.get('Theory'),
            'TechnicalDepth': output_dict.get('TechnicalDepth'),
            'Practicum': output_dict.get('Practicum'),
            'Innovation': output_dict.get('Innovation'),
            'Leadership': output_dict.get('Leadership')
        }

        # Print the created dictionary to verify
        print('Extracted scores: \n', score_dict)
  
        # Clean up the temporary file
        os.remove(temp_file_path)

        # Add the score_dict to the user's "scores" field
        mongo.db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$push": {"scores": score_dict}}
        )
        print(f"Scores {score_dict} added to user {user_id}.")

        track_event(str(user_id), "profile scored", {"action": "score", "new_scores": score_dict})
        # Return the response from Vectorshift
        return jsonify(score_dict), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # Ensure the file is closed
        if 'files' in locals():
            files['Document'].close()