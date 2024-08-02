from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import json
from groq import Groq
import os
from dotenv import load_dotenv
from flask import current_app as app
import re

groq_code_autofill_bp = Blueprint('groq_code_autofill_bp', __name__)

# Load environment variables from .env file
load_dotenv()

client = Groq(
    api_key=os.environ.get("GROQCLOUD_API_KEY"),
)

def summarize_code_description_title_tags(text):
    try:
        print('Got to summarize_code_description_title_tags')
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content. Write from the first person and all responses should be JSON format."
                },
                {
                    "role": "user",
                    "content": f"For the following code files, please write a concise (less than 400 words) description for this project. Also, provide a list for suggested tags concerning general topics the code is about (tags like: machine learning, computer vision, NLP, robotics, genomics, etc). Lastly please provide a string name for this project. Please always format your response as a json with keys: projectName, tags, and projectDescription. This is very important: the entirety of your response should constitute a valid JSON. There should be no json tags in the front or any leading/trailing text. Only give the json. Here is the text:\n\n{text}"
                }
            ],
            model="llama3-70b-8192",
            max_tokens=600,
            temperature=0.2
        )
        print("SUMMARIZE CODE DESCRIPTION TITLE TAGS here is the response: ", response.choices[0].message.content.strip())
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error summarizing code description: {e}")
        return '{}'

def summarize_code_layers(text):
    try:
        print('Got to summarize_code_layers')
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content. Return everything in a valid JSON format and write from the first person."
                },
                {
                    "role": "user",
                    "content": f"I need to create a project page by summarizing the following code into multiple self-contained sections. Each section should be long and detailed. Please provide the following sections: abstract, methodology, future work, results, and another relevant topic. Format the response as a JSON array where each object has a key representing the section title (e.g., ‘abstract’, ‘methodology’, ‘future work’, ‘results’, and a header for the last topic) and a 'content' key containing the paragraph text. So it should resemble something like this:  [ {{ 'abstract': 'text' }}, {{ 'methodology': 'text' }}, {{ 'future work': 'text' }}, {{ 'results': 'text' }}, {{ 'additional topic': 'text' }} ] Do not include any additional text or formatting outside the JSON array. Ensure there are no JSON tags or extraneous text. Only provide the JSON array. Here is the text:\n\n{text}"
                }
            ],
            model="llama3-8b-8192",
            max_tokens=1800,
            temperature=0.2
        )
        message_content = response.choices[0].message.content.strip()
        print('here is the layers summarized: ', message_content)

        message_content = remove_trailing_commas(message_content)
        
        # Validate and parse JSON format
        try:
            json_content = json.loads(message_content)
            print('here is json content: ', json_content)
        except json.JSONDecodeError as e:
            print(f"JSONDecodeError: {e}")
            return []  # Return an empty list if there's an error
        
        return json_content
    except Exception as e:
        print(f"Error summarizing code layers: {e}")
        return []

def validate_and_correct_json(json_str):
    try:
        json_obj = json.loads(json_str)
        return json.dumps(json_obj)
    except json.JSONDecodeError:
        return '{}'

def remove_trailing_commas(json_str):
    # Regular expression to match and remove trailing commas before closing braces and brackets
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
    return json_str

def validate_json(json_str):
    try:
        json.loads(json_str)
        return True
    except json.JSONDecodeError:
        return False

def validate_and_regenerate_json(combined_code):
    surrounding_summary = summarize_code_description_title_tags(combined_code)
    summary_content = summarize_code_layers(combined_code)

    if not validate_json(surrounding_summary):
        print("Invalid JSON for surrounding_summary, regenerating...")
        surrounding_summary = summarize_code_description_title_tags(combined_code)

    if not validate_json(json.dumps(summary_content)):
        print("Invalid JSON for summary_content, regenerating...")
        summary_content = summarize_code_layers(combined_code)

    return surrounding_summary, summary_content

@groq_code_autofill_bp.route('/groqAutofillCodeProject', methods=['POST'])
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

        surrounding_summary, summary_content = validate_and_regenerate_json(combined_code)

        print(f'here is the surrounding_summary: {surrounding_summary}')
        print(f'here is the summary_content: {summary_content}')

        return jsonify({
            'surrounding_summary': json.loads(surrounding_summary), 
            'summary_content': summary_content
        }), 200

    except Exception as e:
        print(f"Error processing code files: {e}")
        return jsonify({'error': 'Failed to process code files'}), 500
