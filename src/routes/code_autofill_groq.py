from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import json
from groq import Groq
import openai
import os
from dotenv import load_dotenv
from flask import current_app as app
import re
import requests
import base64
import sys


groq_code_autofill_bp = Blueprint('groq_code_autofill_bp', __name__)
GITHUB_API_TOKEN = os.environ.get("GITHUB_API_TOKEN")
openai.api_key = os.environ.get("OPENAI_API_KEY")

# Load environment variables from .env file
load_dotenv()

client = Groq(
    api_key=os.environ.get("GROQCLOUD_API_KEY"),
)

groq_limit = 4000

OpenAILimit = 10000

maxLimit = 30000

def groq_summarize_code_description_title_tags(text):
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
                    "content": f"For the following code files, please write a concise (less than 900 words) description for this project. Also, provide a list for suggested tags concerning general topics the code is about (tags like: machine learning, computer vision, NLP, robotics, genomics, etc). Lastly please provide a string name for this project. Please always format your response as a json with keys: projectName, tags, and projectDescription. This is very important: the entirety of your response should constitute a valid JSON. There should be no json tags in the front or any leading/trailing text. Only give the json. Make it somewhat detailed. Here is the text:\n\n{text}"
                }
            ],
            model="llama3-8b-8192",
            max_tokens=600,
            temperature=0.2
        )
        return json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        print(f"Error summarizing code description: {e}")
        return {}

def groq_summarize_code_layers(text):
    try:
        print('Got to summarize_code_layers')
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content. Return everything in a valid JSON format and write from the first person. Write with detail and make each section long."
                },
                {
                    "role": "user",
                    "content": f"I need to create a project page by summarizing the following code into multiple self-contained sections. Each section should be long and detailed. Please provide the following sections: Description, Methodology, Purpose, Extensions, and another section that is relevant to the code context. Format the response as a JSON object where each key represents the section title and the value contains the content. Each section should be long and detailed. Ensure there are no JSON tags or extraneous text. Only provide the JSON object. Here is the code:\n\n{text}"}
            ],
            model="llama3-8b-8192",
            max_tokens=5000,
            temperature=0.2
        )
        content = response.choices[0].message.content.strip()
        
        # Remove newlines and carriage returns
        content = content.replace('\n', '').replace('\r', '')
        
        # Remove trailing commas before closing braces
        content = re.sub(r',\s*}', '}', content)
        
        # Check for and add missing closing brace
        if content.count('{') > content.count('}'):
            content += '}'
        
        # Use a more lenient JSON parsing method
        parsed_content = json.loads(content, strict=False)
        
        return parsed_content

    except json.JSONDecodeError as e:
        print(f"JSON Decode Error: {e}")
        print(f"Problematic content: {content}")
        # Attempt to extract valid JSON
        try:
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                extracted_json = match.group(0)
                return json.loads(extracted_json, strict=False)
        except:
            pass
    except Exception as e:
        print(f"Error summarizing code layers: {e}")
    
    # Return default structure if all parsing attempts fail
    return {
        "Description": "Error occurred during summarization",
        "Methodology": "Error occurred during summarization",
        "Purpose": "Error occurred during summarization",
        "Extensions": "Error occurred during summarization",
        "Tags": []
    }



def openai_summarize_code_description_title_tags(text):
    try:
        print('Got to summarize_code_description_title_tags')
        response = openai.ChatCompletion.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content. Write from the first person and all responses should be JSON format."
                },
                {
                    "role": "user",
                    "content": f"For the following code files, please write a concise (less than 900 words) description for this project. Also, provide a list for suggested tags concerning general topics the code is about (tags like: machine learning, computer vision, NLP, robotics, genomics, etc). Lastly please provide a string name for this project. Please always format your response as a json with keys: projectName, tags, and projectDescription. This is very important: the entirety of your response should constitute a valid JSON. There should be no json tags in the front or any leading/trailing text. Only give the json. Make it somewhat detailed. Here is the text:\n\n{text}"
                }
            ],
            model="gpt-4o-mini",
            max_tokens=600,
            temperature=0.2
        )
        return json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        print(f"Error summarizing code description: {e}")
        return {}

def openai_summarize_code_layers(text):
    try:
        print('Got to summarize_code_layers')
        response = openai.ChatCompletion.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content. Return everything in a valid JSON format and write from the first person. Write with detail and make each section long."
                },
                {
                    "role": "user",
                    "content": f"I need to create a project page by summarizing the following code into multiple self-contained sections. Each section should be long and detailed. Please provide the following sections: Description, Methodology, Purpose, Extensions, and another section that is relevant to the code context. Format the response as a JSON object where each key represents the section title and the value contains the content. Each section should be long and detailed. Ensure there are no JSON tags or extraneous text. Only provide the JSON object. Here is the code:\n\n{text}"}
            ],
            model="gpt-4o-mini",
            max_tokens=5000,
            temperature=0.2
        )
        content = response.choices[0].message.content.strip()
        
        # Remove newlines and carriage returns
        content = content.replace('\n', '').replace('\r', '')
        
        # Remove trailing commas before closing braces
        content = re.sub(r',\s*}', '}', content)
        
        # Check for and add missing closing brace
        if content.count('{') > content.count('}'):
            content += '}'
        
        # Use a more lenient JSON parsing method
        parsed_content = json.loads(content, strict=False)
        
        return parsed_content

    except json.JSONDecodeError as e:
        print(f"JSON Decode Error: {e}")
        print(f"Problematic content: {content}")
        # Attempt to extract valid JSON
        try:
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                extracted_json = match.group(0)
                return json.loads(extracted_json, strict=False)
        except:
            pass
    except Exception as e:
        print(f"Error summarizing code layers: {e}")
    
    # Return default structure if all parsing attempts fail
    return {
        "Description": "Error occurred during summarization",
        "Methodology": "Error occurred during summarization",
        "Purpose": "Error occurred during summarization",
        "Extensions": "Error occurred during summarization",
        "Tags": []
    }



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
    code_length = len(combined_code)

    groq_char_limit = OpenAILimit * 4
    openai_char_limit = maxLimit * 4

    print(f"Code length: {code_length} characters")
    
    if code_length < groq_char_limit:
        print("Using Groq for summarization")
        surrounding_summary = groq_summarize_code_description_title_tags(combined_code)
        summary_content = groq_summarize_code_layers(combined_code)
    elif code_length < openai_char_limit:
        print("Using OpenAI for summarization")
        surrounding_summary = openai_summarize_code_description_title_tags(combined_code)
        summary_content = openai_summarize_code_layers(combined_code)
    else:
        print("Code length exceeds maximum limit")
        return {"error": "Code length exceeds maximum limit for summarization"}, {"error": "Code length exceeds maximum limit for summarization"}
    return surrounding_summary, summary_content

@groq_code_autofill_bp.route('/groqAutofillCodeProject', methods=['POST'])
@cross_origin()
def autofill_code_project():
    data = request.get_json()
    print('autofill code project data: ', data)
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    owner = data.get('owner_name')
    repo = data.get('repo_name')
    branch = data.get('branch_name')
    file_names = data.get('file_names')

    print(f"Owner: {owner}, Repo: {repo}, Branch: {branch}")
    print(f"File names: {file_names}")

    if not all([owner, repo, branch, file_names]):
        return jsonify({'error': 'Incomplete data provided'}), 400

    try:
        combined_code = ""
        fetched_files = 0
        for file_name in file_names:
            print(f"Attempting to fetch file: {file_name}")
            content = get_file_content_from_github(owner, repo, branch, file_name)
            if content:
                combined_code += f"\n\n# {file_name}\n\n{content}\n\n\n"
                fetched_files += 1
                print(f"Successfully fetched content for {file_name}")
            else:
                print(f"Warning: Failed to fetch content for {file_name}")

        if fetched_files == 0:
            return jsonify({'error': 'Failed to fetch content for any files'}), 500

        print(f"Successfully fetched {fetched_files} out of {len(file_names)} files")

        surrounding_summary, summary_content = validate_and_regenerate_json(combined_code)
        summary_content_array = [[key, value] for key, value in summary_content.items()] if summary_content else []
        return jsonify({
            'surrounding_summary': surrounding_summary, 
            'summary_content': summary_content_array
        }), 200

    except Exception as e:
        print(f"Error processing code files: {e}")
        return jsonify({'error': 'Failed to process code files'}), 500


def get_file_content_from_github(owner, repo, branch, file_path):
    # Remove the repository name from the beginning of the file_path if it's there
    if file_path.startswith(f"{repo}/"):
        file_path = file_path[len(repo)+1:]

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}?ref={branch}"
    headers = {"Authorization": f"token {GITHUB_API_TOKEN}"} if GITHUB_API_TOKEN else {}
    
    try:
        print(f"Requesting URL: {url}")  # Add this line for debugging
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # This will raise an exception for 4xx and 5xx status codes
        content = response.json()['content']
        return base64.b64decode(content).decode('utf-8')
    except requests.exceptions.RequestException as e:
        print(f"Error fetching file: {file_path}. Error: {str(e)}")
        print(f"Full URL: {url}")
        if response.status_code == 404:
            print("File not found. Please check if the file path is correct.")
        elif response.status_code == 403:
            print("Access forbidden. Check your GitHub API token permissions.")
        return None