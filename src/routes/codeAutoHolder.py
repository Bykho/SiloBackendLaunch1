from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import json
import os
import re
import openai
import concurrent.futures
from dotenv import load_dotenv
from groq import Groq

codeAutoHolder = Blueprint('codeAutoHolder', __name__)

# Load environment variables from .env file
load_dotenv()

client = Groq(api_key=os.environ.get("GROQCLOUD_API_KEY"))
openai.api_key = os.getenv("OPENAI_API_KEY")

groq_limit = 6000
OpenAILimit = 15000
chunkLimit = 25000

# Utility function to remove trailing commas in JSON
def remove_trailing_commas(json_str):
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
    return json_str

# Utility function to split text into chunks
def split_into_chunks(text, chunk_size):
    chunks = []
    while text:
        chunk = text[:chunk_size]
        text = text[chunk_size:]
        chunks.append(chunk)
    return chunks

# Utility function to validate JSON format
def validate_json(json_str):
    try:
        json.loads(json_str)
        return True
    except json.JSONDecodeError:
        return False

# Groq summarization functions
def groq_summarize_code_description_title_tags(text):
    print('groq_summarize_code_description_title_tags')
    try:
        response = client.chat.completions.create(
            model="llama3-70b-8192",
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
            max_tokens=600,
            temperature=0.2
        )
        print('groq_summarize_code_description_title_tags: response.choices[0].message.content.strip(), ', response.choices[0].message.content.strip())
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error summarizing code description: {e}")
        return {}

def groq_summarize_code_layers(text):
    print('groq_summarize_code_layers')
    try:
        response = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content. Return everything in a valid JSON format and write from the first person."
                },
                {
                    "role": "user",
                    "content": f"I need to create a project page by summarizing the following code into multiple self-contained sections. Each section should be long and detailed. Please provide the following sections: abstract, methodology, future work, results, and another relevant topic. Format the response as a JSON array where each object has a key representing the section title (e.g., ‘abstract’, ‘methodology’, ‘future work’, ‘results’, and a header for the last topic) and a 'content' key containing the paragraph text. Do not include any additional text or formatting outside the JSON array. Ensure there are no JSON tags or extraneous text. Only provide the JSON array. Here is the text:\n\n{text}"
                }
            ],
            max_tokens=1800,
            temperature=0.2
        )
        message_content = response.choices[0].message.content.strip()
        message_content = remove_trailing_commas(message_content)
        print('groq_summarize_code_layers: message_content, ', message_content)
        return message_content
    except Exception as e:
        print(f"Error summarizing code layers: {e}")
        return []

# OpenAI summarization functions
def OpenAI_summarize_code_description_title_tags(text):
    print('OpenAI_summarize_code_description_title_tags')
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content. Write from the first person and all responses should be JSON format."
                },
                {
                    "role": "user",
                    "content": f"For the following code files, please write a concise (less than 100 words) description for this project. Also, provide a list for suggested tags concerning general topics the code is about (tags like: machine learning, computer vision, NLP, robotics, genomics, etc). Lastly please provide a string name for this project. Please always format your response as a json with keys: projectName, tags, and projectDescription. This is very important: the entirety of your response should constitute a valid JSON. There should be no json tags in the front or any leading/trailing text. Only give the json. Here is the text:\n\n{text}"
                }
            ],
            max_tokens=600,
            temperature=0.2
        )
        message_content = response.choices[0].message['content'].strip()
        message_content = remove_trailing_commas(message_content)

        try: 
            toReturn =  json.loads(message_content)
        except json.JSONDecodeError as e:
            print(f"JSONDecodeError: {e}")
            return {}
        return toReturn
    except Exception as e:
        print(f"Error summarizing code description: {e}")
        return {}

def OpenAI_summarize_code_layers(text):
    print('OpenAI_summarize_code_layers')
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content. Return everything in a valid JSON format and write from the first person."
                },
                {
                    "role": "user",
                    "content": f"I need to create a project page by summarizing the following code into multiple self-contained sections. Each section should be long and detailed. Please provide the following sections: abstract, methodology, future work, results, and another relevant topic. Format the response as a JSON array where each object has a key representing the section title (e.g., ‘abstract’, ‘methodology’, ‘future work’, ‘results’, and a header for the last topic) and a 'content' key containing the paragraph text. Do not include any additional text or formatting outside the JSON array. Ensure there are no JSON tags or extraneous text. Only provide the JSON array. Here is the text:\n\n{text}"
                }
            ],
            max_tokens=1200,
            temperature=0.2
        )
        message_content = response.choices[0].message['content'].strip()
        message_content = remove_trailing_commas(message_content)
        if not message_content.endswith(']'):
            message_content += ']'
        try:
            toReturn = json.loads(message_content)
            print('here is json content: ', toReturn)
        except json.JSONDecodeError as e:
            print(f"JSONDecodeError: {e}")
            return []  # Return an empty JSON array if there's an error
        
        return toReturn
    except Exception as e:
        print(f"Error summarizing text: {e}")
        return []


def chunking_summarize(text, chunk_size=9000):
    sub_sections = split_into_chunks(text, chunk_size)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        summarized_sub_sections = list(executor.map(summarize_sub_section, sub_sections))
    aggregated_summary = ' '.join(summarized_sub_sections)
    summary_layers = OpenAI_summarize_code_layers(aggregated_summary)
    surrounding_summary = OpenAI_summarize_code_description_title_tags(aggregated_summary)
    return surrounding_summary, summary_layers

# Summarizes a sub-section of text using the OpenAI API
def summarize_sub_section(sub_section):
    print('summarize_sub_section')
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Please summarize the following content and keep it short but relevant. Keep it to be around 400 words."},
                {"role": "user", "content": f"{sub_section}"}
            ],
            max_tokens=600,
            temperature=0.2
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        print(f"Error summarizing sub-section: {e}")
        return ""

# Main function to validate and regenerate JSON summaries
def validate_and_regenerate_json(combined_code):
    def sizeSplitter(combined_code):
        if len(combined_code) < groq_limit:
            print()
            print()
            print('validate_and_regenerate_json: combined code was under groq_limit')
            print()
            summary_description = groq_summarize_code_description_title_tags(combined_code)
            summary_layers = groq_summarize_code_layers(combined_code)
            return summary_description, json.loads(summary_layers)
        elif groq_limit < len(combined_code) < OpenAILimit:
            print()
            print()
            print('validate_and_regenerate_json: combined code was under OpenAILimit')
            print()
            summary_description = OpenAI_summarize_code_description_title_tags(combined_code)
            summary_layers = OpenAI_summarize_code_layers(combined_code)
            return summary_description, summary_description
        elif OpenAILimit < len(combined_code) < chunkLimit:
            print()
            print()
            print('validate_and_regenerate_json: combined code was under chunkLimit')
            print()
            surrounding_summary, summary_layers = chunking_summarize(combined_code)
            return surrounding_summary, summary_layers
        else:
            print('Size was too large for chunking')
            raise ValueError("The combined code exceeds the maximum allowed limit for processing.")

    surrounding_summary, summary_content = sizeSplitter(combined_code)
    print('Surrounding Summary:', surrounding_summary)
    print('Summary Content:', summary_content)

    if not validate_json(json.dumps(surrounding_summary)) or not isinstance(summary_content, list):
        print("Invalid JSON for surrounding_summary or summary_content, regenerating...")
        return sizeSplitter(combined_code)

    return surrounding_summary, summary_content

@codeAutoHolder.route('/newSplittingMethodForCodeAutofill', methods=['POST'])
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

        print(f'Here is the surrounding_summary: {surrounding_summary}')
        print(f'Here is the summary_content: {type(summary_content)}')

        return jsonify({
            'surrounding_summary': surrounding_summary, 
            'summary_content': summary_content
        }), 200

    except Exception as e:
        print(f"Error processing code files: {e}")
        return jsonify({'error': 'Failed to process code files'}), 500

