
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
import json

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
    

def summarize_text_for_sign(text):
    try:
        print('Got to summarize text')
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content."},
                {"role": "user", "content": f"For the following resume, please write a concise (less than 200 words) bio for this person in the first person, also provide lists for suggested interests, suggested skills, a string for their latest university, a string for major, and a string for graduation year. If there are projects on the resume, also include the title of the project and its description (make the description be as long as possible). Please always format your response as a json with keys: bio, skills, interests, latestUniversity, major, grad_yr, projects (with contents title and desc). This is very important: the entirety of your response should constitute a valid JSON. There should be no json tags in the front or any leading/trailing text. Only give the json.  Here is the text:\n\n{text}"}
            ],
            max_tokens=1000,
            n=1,
            stop=None,
            temperature=0.1
        )
        print(f'Here is the response {response}')
        return response.choices[0].message['content'].strip()
    except Exception as e:
        print(f"Error summarizing text: {e}")
        return ""



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
        surrounding_summary = validate_and_correct_json(summarize_text_description_title_tags(file_text))
        summary_content = validate_and_correct_json(summarize_text_layers(file_text))
        print(f'here is the summary_content: {summary_content}')
        print(f'here is the surrounding_summary: {surrounding_summary}')
        return jsonify({'surrounding_summary': surrounding_summary, 'summary_content': summary_content}), 200
    except Exception as e:
        print(f"Error parsing proj file: {e}")
        return jsonify({'error': 'Failed to parse proj file'}), 500

def summarize_text_description_title_tags(text):
    try:
        print('Got to summarize_text_description_title_tags')
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content. Write from the first person and all responses should be JSON format."},
                {"role": "user", "content": f"For the following file, please write a concise (less than 100 words) description for this project. Also, provide a list for suggested tags concerning general topics the file is about (tags like: machine learning, computer vision, NLP, robotics, genomics, etc). Lastly please provide a string name for this project. Please always format your response as a json with keys: name, tags, description. This is very important: the entirety of your response should constitute a valid JSON. There should be no json tags in the front or any leading/trailing text. Only give the json. Here is the text:\n\n{text}"}
            ],
            max_tokens=600,
            n=1,
            stop=None,
            temperature=0.1
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        print(f"Error summarizing text: {e}")
        return '{}'

def summarize_text_layers(text):
    try:
        print('Got to summarize_text_layers')
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content. Return everything in a valid JSON format and write from the first person."},
                {"role": "user", "content": f"I need to create a project page by summarizing the following text into multiple self-contained sections. Please give a section that describes the abstract idea in the text, a section that describes the methodology described in the text, a section that describes the future work in the text, a section describing the results, and another section that describes another topic in the text that is relevant. Make each section long. Please ensure that the entirety of your response is formatted as a valid JSON array with each paragraph as an object containing 'index’, ‘content’, and ‘header’ keys. The ‘header’ field should include what section of the project it is between ‘abstract’, ‘methodology’, ‘future work’, ‘results’, and the other topic. Do not include any additional text outside of the JSON array. There should be no json tags in the front or any leading/trailing text. Only give the json. THERE SHOULD BE NO: ```json in the response. Here is the text:\n\n{text}"}
            ],
            max_tokens=1800,
            n=1,
            stop=None,
            temperature=0.1
        )

        message_content = response.choices[0].message['content'].strip()
        print('here is the layers summarized: ', message_content)
        # Validate JSON format
        try:
            json_content = json.loads(message_content)
            print('here is json content: ', json_content)
        except json.JSONDecodeError as e:
            print(f"JSONDecodeError: {e}")
            return json.dumps([])  # Return an empty JSON array if there's an error
        return message_content
    except Exception as e:
        print(f"Error summarizing text: {e}")
        return json.dumps([])  # Return an empty JSON array if there's an error


def validate_and_correct_json(json_str):
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"Initial JSONDecodeError: {e}")
        truncated_pos = e.pos
        print(f"Truncated position: {truncated_pos}")
        
        # Trim the JSON string up to the last complete section
        truncated_str = json_str[:truncated_pos].rstrip(', ')
        
        # Close the JSON array properly
        if truncated_str.endswith('}'):
            truncated_str = truncated_str.rsplit(',', 1)[0] + ']}'
        elif truncated_str.endswith(']'):
            truncated_str = truncated_str.rsplit(',', 1)[0] + ']'
        else:
            truncated_str += ']'
        
        print(f"Truncated and corrected JSON string: {truncated_str}")
        
        # Attempt to parse the corrected JSON string
        try:
            return json.loads(truncated_str)
        except json.JSONDecodeError as e:
            print(f"Final JSONDecodeError: {e}")
            return []



@autofiller_bp.route('/autofillCodeProject', methods=['POST'])
@cross_origin()
def autofill_code_project():
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    user = data.get('user')
    projects = data.get('projects')

    if not user or not projects:
        return jsonify({'error': 'Incomplete data provided'}), 400

    try:
        # Combine all code files into one large string
        combined_code = ""
        for project in projects:
            content = project['content']
            combined_code += f"\n\n# {project['repoName']}/{project['filePath']}\n\n" + content + "\n\n\n"

        # Call OpenAI API to process the combined code
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content. Return everything in a valid JSON format and write from the first person."},
                {"role": "user", "content": f"Analyze the following combined code files and respond in a JSON format. The JSON should have the following keys 'abstract summary', 'methodology', 'approach', and 'purpose'. There might be code from multiple files in this project. Treat each code file as if it were relating to the same project. Have each value in the JSON be long. Start the abstract with 'In this project...'. Here is the code:\n\n{combined_code}"},
            ],
            max_tokens=1500,
            n=1,
            stop=None,
            temperature=0.1
        )
        
        returned_summary = response.choices[0].message['content'].strip()
        summary_json = json.loads(returned_summary)
        
        summary_array = [[key, value] for key, value in summary_json.items()]
        print('here is the project summarized as array: ', summary_array)

        return jsonify({'message': 'Files processed successfully', 'summary': summary_array}), 200

    except Exception as e:
        print(f"Error processing code files: {e}")
        return jsonify({'error': 'Failed to process code files'}), 500


