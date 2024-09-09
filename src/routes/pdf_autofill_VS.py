


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
import base64

load_dotenv()

VS_pdf_autofill_bp = Blueprint('VS_pdf_autofill_bp', __name__)
@VS_pdf_autofill_bp.route('/VS_pdfPipe_large', methods=['POST'])
def pdf_autofill_VS_bp():
    print('opened the route')
    file = request.files.get('file')
    print('got the file')
    api_key = os.getenv("VECTORSHIFT_API_KEY")
    print('got the key')

    if not api_key or len(api_key.strip()) == 0:
        return jsonify({"error": "Invalid API key"}), 500

    if not file:
        return jsonify({"error": "No file provided"}), 400


    try:
        print('got to the file.read()')
        file_content = file.read()
        print('got passed the file.read() function')
        print('here is the type(file), ', file)

        url = "https://api.vectorshift.ai/api/pipelines/run"
        headers = {
            "Api-Key": api_key,
        }
        data = {
            "inputs": json.dumps({
                "input_1": "Provide a high-level summary of the entire file. Focus on the overall functionality, purpose, and main components of the project. Describe the project's goals, the problem it solves, and how the project is structured to achieve these goals. Make it long. This entry should be a string with the key ‘Description’.",
                "input_2": "Break down the specific methods and approaches used in the project. This should include explanations of the algorithms, design patterns, or architectural decisions that were implemented. Discuss how these methods contribute to the overall functionality and efficiency of the project. This entry should be a string with the key ‘Methodology’.",
                "input_3": "Generate a concise description of the purpose of the project. This entry should be a string with the key ‘Purpose’.",
                "input_4": "Generate a concise project name and a list of relevant tags that categorize the project's technical domains. The tags should reflect the key topics the project addresses, such as 'machine learning', 'computer vision', 'NLP', etc. This entry should be a string with the key ‘Tags’.",
                "input_5": "Identify potential areas of improvement or expansion for the project. Do not write a list, write this in paragraph form (not bullet points). This entry should be a properly formatted paragraph with the key ‘Extensions’. Again, do not write a list.",
                "LLMSystem": "You are a helpful assistant that extracts information explained in the Tasks from a document contained in the Context and returns a perfect JSON with the responses. Do not have any trailing apostrophes or say the word ‘JSON’. Just give me the dictionary that would work for the function JSON.loads(). That dictionary should have the following keys: ‘Description’ , ‘Methodology’,  ‘Purpose’, ‘Extensions’, and ‘Tags’ with the value being an array of relevant topics. Make it be a perfect JSON dictionary with everything properly formatted. Do not include any newline characters or unescaped double quotes. I should be able to take the output, insert it into JSON.loads() and get no errors.",
                "Surrounding_summary_input": "For the following files, please write a relevant and long description for this project. Also, provide a list for suggested tags concerning general topics the project is about (tags like: machine learning, computer vision, NLP, robotics, genomics, etc). Lastly please provide a string name for this project. Please always format your response as a json with keys: name, tags, and description. This is very important: the entirety of your response should constitute a valid JSON. There should be no json tags in the front or any leading/trailing text. Only give the json.",
                "Surrounding_summary_system": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content. Write from the first person and use proper JSON formatting. You should have the following keys: projectName, tags, and projectDescription. There should be no other keys at all. Only have those keys.",
                }),
            "pipeline_name": "PDF Pipe Large",
            "username": "bykho",
        }

        files = {
            "LargeFile": (file.filename, file, file.content_type)
        }

        response = requests.post(url, headers=headers, data=data, files=files)
        response.raise_for_status()
        print('got passed the data')
        response = response.json()
        print('here is the reponse: ', response)
        print()
        openAIOutputDict = json.loads(response['OpenAIOutput'])
        surroundingSummaryDict = json.loads(response['SurroundingSummary_output'])
        #openAIOutputDict_Array = dictionary_to_array(openAIOutputDict)
        openAIOutputDict_Array = openAIOutputDict

        print(f"surroundingSummaryDict: {surroundingSummaryDict} \n \n")
        print(f"openAIOutputDict: {openAIOutputDict} \n \n")
        print(f"")
    except Exception as e:
        return jsonify({"error": f"Failed to process request: {str(e)}"}), 500

    if response.get("error"):
        return jsonify({"error": "Error from VectorShift API", "details": response.get("error")}), 500

    responseDict = {'layers': openAIOutputDict_Array, "summary": surroundingSummaryDict}
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

