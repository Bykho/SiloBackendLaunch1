
from flask import Blueprint, request, jsonify
from flask import current_app as app
from flask_jwt_extended import jwt_required
from .. import mongo
from ..fake_data import sample_users
import copy
from bson import json_util, ObjectId
from flask_cors import cross_origin
import datetime
import openai
import uuid
import hashlib

autofiller_bp = Blueprint('autofiller', __name__)



def convert_objectid_to_str(data):
    if isinstance(data, list):
        return [convert_objectid_to_str(item) for item in data]
    elif isinstance(data, dict):
        return {key: convert_objectid_to_str(value) for key, value in data.items()}
    elif isinstance(data, ObjectId):
        return str(data)
    else:
        return data

@autofiller_bp.route('/resumeParser', methods=['POST', 'OPTIONS'])
@cross_origin()
def resume_parser():
    print('Opened the resume parser route')
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'}), 200
    data = request.get_json()
    if not data or 'resumeText' not in data:
        return jsonify({'error': 'No resume text provided'}), 400
    file_text = data['resumeText']
    try:
        summary = summarize_text_for_sign(file_text)
        print(f'here is the summary: {summary}')
        return jsonify({'summary': summary}), 200
    except Exception as e:
        print(f"Error parsing resume: {e}")
        return jsonify({'error': 'Failed to parse resume'}), 500

@autofiller_bp.route('/projectFileParser', methods=['POST', 'OPTIONS'])
@cross_origin()
def projectFileParser():
    print('Opened the resume parser route')
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'}), 200
    data = request.get_json()
    if not data or 'fileText' not in data:
        return jsonify({'error': 'No fileText provided'}), 400
    file_text = data['fileText']
    try:
        surrounding_summary = summarize_text_description_title_tags(file_text)
        summary_content = summarize_text_layers(file_text)
        print(f'here is the summary_content: {summary_content}')
        return jsonify({'surrounding_summary': surrounding_summary, 'summary_content': summary_content}), 200
    except Exception as e:
        print(f"Error parsing proj file: {e}")
        return jsonify({'error': 'Failed to parse proj file'}), 500
    

def summarize_text_for_sign(text):
    try:
        print('Got to summarize text')
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content."},
                {"role": "user", "content": f"For the following resume, please write a concise (less than 100 words) bio for this person in the first person, also provide lists for suggested interests, suggested skills, a string for their latest university, a string for major, and a string for graduation year. If there are projects on the resume, also include the title of the project and its description. Please always format your response as a json with keys: bio, skills, interests, latestUniversity, major, grad_yr, projects (with contents title and desc). This is very important: the entirety of your response should constitute a valid JSON. There should be no json tags in the front or any leading/trailing text. Only give the json.  Here is the text:\n\n{text}"}
            ],
            max_tokens=600,
            n=1,
            stop=None,
            temperature=0.5
        )
        print(f'Here is the response {response}')
        return response.choices[0].message['content'].strip()
    except Exception as e:
        print(f"Error summarizing text: {e}")
        return ""

# Function to summarize text using OpenAI
def summarize_text_description_title_tags(text):
    try:
        print('Got to summarize_text_description_title_tags')
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content."},
                {"role": "user", "content": f"For the following file, please write a concise (less than 100 words) description for this project. Also, provide a list for suggested tags concerning general topics the file is about (tags like: machine learning, computer vision, NLP, robotics, genomics, etc). Lastly please provide a string name for this project. Please always format your response as a json with keys: name, tags, description. This is very important: the entirety of your response should constitute a valid JSON. There should be no json tags in the front or any leading/trailing text. Only give the json.  Here is the text:\n\n{text}"}            ],
            max_tokens=600,
            n=1,
            stop=None,
            temperature=0.5
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        print(f"Error summarizing text: {e}")
        return ""
    
# Function to summarize text using OpenAI
def summarize_text_layers(text):
    try:
        print('Got to summarize_text_layers')
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content."},
                {"role": "user", "content": f"I need to create a project page by summarizing the following text into multiple self-contained sections. Each section should be around 3 sentences. Make as many sections as necessary. These sections will explain the project in detail when viewed together. Please ensure that the entirety of your response is formatted as a valid JSON array with each paragraph as an object containing 'index' and 'content' keys. Do not include any additional text outside of the JSON array. There should be no json tags in the front or any leading/trailing text. Only give the json. THERE SHOULD BE NO: ```json in the response.   Here is the text:\n\n{text}"}
            ],
            max_tokens=600,
            n=1,
            stop=None,
            temperature=0.5
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        print(f"Error summarizing text: {e}")
        return ""


