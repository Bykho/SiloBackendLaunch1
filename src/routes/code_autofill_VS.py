


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
import re
from io import BytesIO

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

    print(f"Owner_name: {owner_name}, \n Repo_name: {repo_name}, \n Branch_name: {branch_name}, \n File_names: {file_names} \n \n")
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
                "input_3": "Generate a concise description of the purpose of the project. This entry should be a string with the key ‘Purpose’.",
                "input_4": "Generate a concise project name and a list of relevant tags that categorize the project's technical domains. The tags should reflect the key topics the code addresses, such as 'machine learning', 'computer vision', 'NLP', etc. This entry should be a string with the key ‘Tags’.",
                "input_5": "Identify potential areas of improvement or expansion for the project. Do not write a list, write this in paragraph form (not bullet points). This entry should be a properly formatted paragraph with the key ‘Extensions’. Again, do not write a list.",
                "LLMSystem": "You are a helpful assistant that extracts information explained in the Tasks from a document contained in the Context and returns a perfect JSON with the responses. Do not have any trailing apostrophes or say the word ‘JSON’. Just give me the dictionary that would work for the function JSON.loads(). That dictionary should have the following keys: ‘Description’ , ‘Methodology’,  ‘Purpose’, ‘Extensions’, and ‘Tags’ with the value being an array of relevant topics. Make it be a perfect JSON dictionary with everything properly formatted. Do not include any newline characters or unescaped double quotes. I should be able to take the output, insert it into JSON.loads() and get no errors.",
                "Surrounding_summary_input": "For the following code files, please write a concise (less than 400 words) description for this project. Also, provide a list for suggested tags concerning general topics the code is about (tags like: machine learning, computer vision, NLP, robotics, genomics, etc). Lastly please provide a string name for this project. Please always format your response as a json with keys: projectName, tags, and projectDescription. This is very important: the entirety of your response should constitute a valid JSON. There should be no json tags in the front or any leading/trailing text. Only give the json.",
                "Surrounding_summary_system": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content. Write from the first person and use proper JSON formatting. You should have the following keys: projectName, tags, and projectDescription. There should be no other keys at all. Only have those keys.",
                "branch_name": branch_name,
                "file_name": file_names,
                "repo_name": repo_name,
                "owner_name": owner_name,
        }),
            "pipeline_name": "Code Pipe",
            "username": "bykho",
        }
        response = requests.post(url, headers=headers, data=data)
        response = response.json()
        print('here is the reponse: ', response)
        openAIOutputDict = json.loads(response['OpenAIOutput'])
        surroundingSummaryDict = json.loads(response['SurroundingSummary_output'])
        openAIOutputDict_Array = dictionary_to_array(openAIOutputDict)

        print("surroundingSummaryDict: ", surroundingSummaryDict)
    except Exception as e:
        return jsonify({"error": f"Failed to process request: {str(e)}"}), 500

    if response.get("error"):
        return jsonify({"error": "Error from VectorShift API", "details": response.get("error")}), 500

    responseDict = {'summary_content': openAIOutputDict_Array, "surrounding_summary": surroundingSummaryDict}
    return jsonify(responseDict)



def dictionary_to_array(input_dict):
    return [(key, value) for key, value in input_dict.items()]

def print_dict(dictionary):
    for key, values in dictionary.items():
        print(f"{key}\n")
        if isinstance(values, list):  # If the value is a list, print each item on a new line
            for value in values:
                print(value)
        else:  # If the value is not a list, print it directly
            print(values)
        print("\n")  # Print a new line after each key-value pair

