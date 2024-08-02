

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from groq import Groq
import os
from dotenv import load_dotenv
import re
import json

pdf_autofill_groq = Blueprint('pdf_autofill_groq', __name__)

# Load environment variables from .env file
load_dotenv()

client = Groq(
    api_key=os.environ.get("GROQCLOUD_API_KEY"),
)

def summarize_text_description_title_tags(text):
    try:
        print('Got to summarize_text_description_title_tags')
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content. Write from the first person and all responses should be JSON format."},
                {"role": "user", "content": f"For the following file, please write a concise (less than 100 words) description for this project. Also, provide a list for suggested tags concerning general topics the file is about (tags like: machine learning, computer vision, NLP, robotics, genomics, etc). Lastly please provide a string name for this project. Please always format your response as a json with keys: name, tags, description. This is very important: the entirety of your response should constitute a valid JSON. There should be no json tags in the front or any leading/trailing text. Only give the json. Here is the text:\n\n{text}"}
            ],
            model="llama3-70b-8192",
            max_tokens=600,
            temperature=0.2
        )
        message_content = response.choices[0].message.content.strip()
        print(f'Here is the response: {message_content}')
        
        # Remove trailing commas from JSON string
        message_content = remove_trailing_commas(message_content)

        print(f"SUMMARIZE_TEXT_DESCRIPTION_TITLE_TAGS message_content {message_content}")
        
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

def summarize_text_layers(text):
    try:
        print('Got to summarize_text_layers')
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content. Return everything in a valid JSON format and write from the first person."}, 
                {"role": "user", "content": f"I need to create a project page by summarizing the following text into multiple self-contained sections. Each section should be long and detailed. Please provide the following sections: abstract, methodology, future work, results, and another relevant topic. Format the response as a JSON array where each object has a key representing the section title (e.g., ‘abstract’, ‘methodology’, ‘future work’, ‘results’, and a header for the last topic) and a 'content' key containing the paragraph text. Do not include any additional text or formatting outside the JSON array. Ensure there are no JSON tags or extraneous text. Only provide the JSON array. Here is the text:\n\n{text}"}
            ],
            model="llama3-70b-8192",
            max_tokens=1800,
            temperature=0.2
        )
        message_content = response.choices[0].message.content.strip()
        print('here is the layers summarized: ', message_content)

        # Remove trailing commas from JSON string
        message_content = remove_trailing_commas(message_content)

        # Ensure the JSON array is properly closed
        if not message_content.endswith(']'):
            message_content += ']'

        # Validate JSON format
        try:
            json_content = json.loads(message_content)
            print('here is json content: ', json_content)
        except json.JSONDecodeError as e:
            print(f"JSONDecodeError: {e}")
            return []  # Return an empty JSON array if there's an error
        
        return json_content
    except Exception as e:
        print(f"Error summarizing text: {e}")
        return []

def remove_trailing_commas(json_str):
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
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
    surrounding_summary = summarize_text_description_title_tags(file_text)
    summary_content = summarize_text_layers(file_text)

    if not validate_json(json.dumps(surrounding_summary)):
        print("Invalid JSON for surrounding_summary, regenerating...")
        surrounding_summary = summarize_text_description_title_tags(file_text)

    if not validate_json(json.dumps(summary_content)):
        print("Invalid JSON for summary_content, regenerating...")
        summary_content = summarize_text_layers(file_text)

    return surrounding_summary, summary_content

@pdf_autofill_groq.route('/groqProjectFileParser', methods=['POST', 'OPTIONS'])
@cross_origin()
def projectFileParser():
    print('Opened the project file parser route')
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'}), 200
    data = request.get_json()
    if not data or 'fileText' not in data:
        return jsonify({'error': 'No fileText provided'}), 400
    file_text = data['fileText']
    try:
        surrounding_summary, summary_content = validate_and_regenerate_json(file_text)
        print(f'here is the summary_content: {summary_content}')
        print(f'here is the surrounding_summary: {surrounding_summary}')
        return jsonify({'surrounding_summary': surrounding_summary, 'summary_content': summary_content}), 200
    except Exception as e:
        print(f"Error parsing proj file: {e}")
        return jsonify({'error': 'Failed to parse proj file'}), 500


