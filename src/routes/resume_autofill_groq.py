
from flask import Blueprint, request, jsonify
from flask import current_app as app
from flask_cors import cross_origin
from groq import Groq
import os
from dotenv import load_dotenv
import re
import json

resume_autifll_groq = Blueprint('resume_autifll_groq', __name__)

# Load environment variables from .env file
load_dotenv()

client = Groq(
    api_key=os.environ.get("GROQCLOUD_API_KEY"),
)

def summarize_resume_text(text):
    try:
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content."
                },
                {
                    "role": "user",
                    "content": f"For the following resume, please write a concise (less than 200 words) bio for this person in the first person, also provide lists for suggested interests, suggested skills, a string for their latest university, a string for major, and a string for graduation year. If there are projects on the resume, also include the title of the project and its description (make the description be as long as possible). Please always format your response as a json with keys: bio, skills, interests, latestUniversity, major, grad_yr, projects (with contents title and desc). This is very important: the entirety of your response should constitute a valid JSON. There should be no json tags in the front or any leading/trailing text. Only give the json. Here is the text:\n\n{text}"
                }
            ],
            model="llama3-70b-8192",
            max_tokens=1000,
            temperature=0.2
        )
        message_content = response.choices[0].message.content.strip()
        print(f'Here is the response: {message_content}')
        
        # Remove trailing commas from JSON string
        message_content = remove_trailing_commas(message_content)

        print()
        print()
        print(f"SUMMARIZE_RESUME_TEXT message_content {message_content}")
        print()
        print()
        # Validate and parse JSON format
        try:
            json_content = json.loads(message_content)
            print('here is json content: ', json_content)
        except json.JSONDecodeError as e:
            print(f"JSONDecodeError: {e}")
            return {}  # Return an empty dict if there's an error
        
        return json_content
    except Exception as e:
        print(f"Error summarizing text: {e}")
        return {}

def remove_trailing_commas(json_str):
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
    if json_str and json_str[-1] != '}':
        json_str += '}'
    return json_str


def validate_json(json_str):
    try:
        json.loads(json_str)
        return True
    except json.JSONDecodeError:
        return False

def validate_and_correct_json(json_str):
    try:
        json_obj = json.loads(json_str)
        return json.dumps(json_obj)
    except json.JSONDecodeError:
        return '{}'

def validate_and_regenerate_json(file_text):
    summary = summarize_resume_text(file_text)

    if not validate_json(json.dumps(summary)):
        print("Invalid JSON for summary, regenerating...")
        summary = summarize_resume_text(file_text)

    return summary

@resume_autifll_groq.route('/groqResumeParser', methods=['POST', 'OPTIONS'])
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
        summary = validate_and_regenerate_json(file_text)
        print(f'here is the summary: {summary}')
        return jsonify({'summary': summary}), 200
    except Exception as e:
        print(f"Error parsing resume: {e}")
        return jsonify({'error': 'Failed to parse resume'}), 500
    

