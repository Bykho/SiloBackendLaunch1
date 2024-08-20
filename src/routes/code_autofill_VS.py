


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
from io import BytesIO


# Load environment variables from .env file
load_dotenv()

VS_code_autofill_bp = Blueprint('VS_code_autofill_bp', __name__)

@VS_code_autofill_bp.route('/VS_code_autofill_bp', methods=['POST'])
def code_autofill_VS_bp():
    data = request.json
    branch_name = data.get('branch_name')
    file_names = data.get('file_names')
    extracted_file_names = [file_name.split('/')[-1] for file_name in file_names]
    joined_file_names = '\n'.join(extracted_file_names).replace(" ", "")
    file_names = joined_file_names
    repo_name = data.get('repo_name')
    owner_name = data.get('owner_name')

    print(f"Owner_name: {owner_name}, \n Repo_name: {repo_name}, \n Branch_name: {branch_name}, \n File_names: {file_names}")
    api_key = os.getenv("VECTORSHIFT_API_KEY")

    if not api_key or len(api_key.strip()) == 0:
        return jsonify({"error": "Invalid API key"}), 500


    try:
        url = "https://api.vectorshift.ai/api/pipelines/run"
        headers = {
            "Api-Key": api_key,
        }
        data = {
            "inputs": json.dumps({
                "input_1": "Provide a high-level summary of the entire codebase. Focus on the overall functionality, purpose, and main components of the project. Describe the project's goals, the problem it solves, and how the code is structured to achieve these goals. Make it long. This entry should be a string with the key ‘Description’.",
                "input_2": "Break down the specific methods and approaches used in the code. This should include explanations of the algorithms, design patterns, or architectural decisions that were implemented. Discuss how these methods contribute to the overall functionality and efficiency of the project. This entry should be a string with the key ‘Methodology’.",
                "input_3": "Generate a concise description of the intention by hind the project. This should largely detail the purpose of the project. This entry should be a string with the key ‘Purpose’.",
                "input_4": "Generate a concise project name and a list of relevant tags that categorize the project's domain. The tags should reflect the key topics the code addresses, such as 'machine learning', 'computer vision', 'NLP', etc. This entry should be a string with the key ‘Tags’.",
                "input_5": "Identify potential areas of improvement or expansion for the project. This section should highlight any limitations of the current implementation and suggest future enhancements or directions that could be taken to build upon the existing code. This entry should be a string with the key ‘Future Work’.",
                "LLMSystem": "You are a helpful assistant that extracts information explained in the Tasks from a document contained in the Context and returns a perfect JSON with the responses. Do not have any trailing apostrophes or say the word ‘JSON’. Just give me the dictionary that would work for JSON. That dictionary should have the following keys: ‘Description’ with the value being a string, ‘Methodology’ with the value being a string, ‘Purpose’ with the value being a string, ‘Tags’ with the value being an array of relevant topics, and ‘Future Work’ with the value being a string describing ways this project could be extended. Make it be a perfect JSON dictionary.",
                "branch_name": branch_name,
                "file_name": file_names,
                "repo_name": repo_name,
                "owner_name": owner_name,
        }),
            "pipeline_name": "Code Pipe",
            "username": "bykho",
        }
        response = requests.post(url, headers=headers, data=data)
        print('Here is the first response')
        print(f"{response}")
        print()
        response = response.json()
        print('Here is the second response')
        print(f"{response}")
        print()
        print(f'here is the type for the response {type(response)} \n')
        print('here is response[AnthropicOutput]')
        print(f"{response['AnthropicOutput']}")
        print()
        print('here is response[OpenAIOutput]')
        print(f"{response['OpenAIOutput']} \n here is type(response['OpenAIOutput']): {type(response['OpenAIOutput'])}")
        print(f"{response['AnthropicOutput']} \n here is type(response['AnthropicOutput']): {type(response['AnthropicOutput'])}")
        print(f" \n here is type(response[OpenAIOutput][Tags]) \n {type(response['OpenAIOutput']['Tags'])} \n ")
        print(f" here is type(response[AnthropicOutput][Tags]) \n {type(response['AnthropicOutput']['Tags'])} \n ")

    except Exception as e:
        return jsonify({"error": f"Failed to process request: {str(e)}"}), 500

    if response.get("error"):
        return jsonify({"error": "Error from VectorShift API", "details": response.get("error")}), 500

    # Proceed with further processing or return the relevant data
    return jsonify(response)
