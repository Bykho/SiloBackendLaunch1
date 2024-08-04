


from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import openai
from groq import Groq
import os
from dotenv import load_dotenv
import re
import json
import concurrent.futures

pdf_autofill_groq = Blueprint('pdf_autofill_groq', __name__)

# Load environment variables from .env file
load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

client = Groq(
    api_key=os.environ.get("GROQCLOUD_API_KEY"),
)

groq_limit = 8000
OpenAILimit = 50000
chunkLimit = 120000

# Removes trailing commas from a JSON string
def remove_trailing_commas(json_str):
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
    return json_str

# Validates if a string is a valid JSON
def validate_json(json_str):
    try:
        json.loads(json_str)
        return True
    except json.JSONDecodeError:
        return False

# Splits text into chunks of a specified size
def split_into_chunks(text, chunk_size):
    chunks = []
    while text:
        chunk = text[:chunk_size]
        text = text[chunk_size:]
        chunks.append(chunk)
    return chunks

# Summarizes the text to get a description, tags, and name for the project
def groq_summarize_text_description_title_tags(text):
    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content. Write from the first person and all responses should be JSON format."},
                {"role": "user", "content": f"For the following file, please write a concise (less than 100 words) description for this project. Also, provide a list for suggested tags concerning general topics the file is about (tags like: machine learning, computer vision, NLP, robotics, genomics, etc). Lastly please provide a string name for this project. Please always format your response as a json with keys: name, tags, description. This is very important: the entirety of your response should constitute a valid JSON. There should be no json tags in the front or any leading/trailing text. Only give the json. Here is the text:\n\n{text}"}
            ],
            model="llama3-70b-8192",
            max_tokens=900,
            temperature=0.2
        )
        message_content = response.choices[0].message.content.strip()
        message_content = remove_trailing_commas(message_content)
        
        try:
            json_content = json.loads(message_content)
        except json.JSONDecodeError as e:
            return {}
        
        return json_content
    except Exception as e:
        return {}

# Summarizes the text into detailed sections like abstract, methodology, future work, results
def groq_summarize_text_layers(text):
    try:
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
        message_content = remove_trailing_commas(message_content)
        if not message_content.endswith(']'):
            message_content += ']'
        try:
            json_content = json.loads(message_content)
        except json.JSONDecodeError as e:
            return []  # Return an empty JSON array if there's an error
        
        return json_content
    except Exception as e:
        return []


# Summarizes the text to get a description, tags, and name for the project using OpenAI
def openai_summarize_text_description_title_tags(text):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content. Write from the first person and all responses should be JSON format."},
                {"role": "user", "content": f"For the following file, please write a concise (less than 100 words) description for this project. Also, provide a list for suggested tags concerning general topics the file is about (tags like: machine learning, computer vision, NLP, robotics, genomics, etc). Lastly please provide a string name for this project. Please always format your response as a json with keys: name, tags, description. This is very important: the entirety of your response should constitute a valid JSON. There should be no json tags in the front or any leading/trailing text. Only give the json. Here is the text:\n\n{text}"}
            ],
            max_tokens=900,
            temperature=0.2
        )
        message_content = response.choices[0].message['content'].strip()
        
        # Remove trailing commas from JSON string
        message_content = remove_trailing_commas(message_content)

        # Validate and parse JSON format
        try:
            json_content = json.loads(message_content)
        except json.JSONDecodeError as e:
            return {}  # Return an empty dict if there's an error
        
        return json_content
    except Exception as e:
        return {}
    

# Summarizes the text into detailed sections like abstract, methodology, future work, results using OpenAI
def openai_summarize_text_layers(text):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content. Return everything in a valid JSON format and write from the first person."}, 
                {"role": "user", "content": f"I need to create a project page by summarizing the following text into multiple self-contained sections. Each section should be long and detailed. Please provide the following sections: abstract, methodology, future work, results, and another relevant topic. Format the response as a JSON array where each object has a key representing the section title (e.g., ‘abstract’, ‘methodology’, ‘future work’, ‘results’, and a header for the last topic) and a 'content' key containing the paragraph text. Do not include any additional text or formatting outside the JSON array. Ensure there are no JSON tags or extraneous text. Only provide the JSON array. Here is the text:\n\n{text}"}
            ],
            max_tokens=1800,
            temperature=0.2
        )
        message_content = response.choices[0].message['content'].strip()

        # Remove trailing commas from JSON string
        message_content = remove_trailing_commas(message_content)
        if not message_content.endswith(']'):
            message_content += ']'
        
        # Validate JSON format
        try:
            json_content = json.loads(message_content)
        except json.JSONDecodeError as e:
            return []  # Return an empty JSON array if there's an error
        
        return json_content
    except Exception as e:
        return []



# Summarizes a sub-section of text using the OpenAI API
def summarize_sub_section(sub_section):
    print('summarizing sub_section')
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
        return ""

# Splits the text into sub-sections, summarizes each sub-section in parallel, and aggregates the summaries
def summarize_sub_sections(text, chunk_size=20000):
    sub_sections = split_into_chunks(text, chunk_size)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        summarized_sub_sections = list(executor.map(summarize_sub_section, sub_sections))
    aggregated_summary = ' '.join(summarized_sub_sections)
    return aggregated_summary

# Main function to validate and regenerate JSON summaries
def validate_and_regenerate_json(file_text):
    def sizeSplitter(combined_code):
        if len(combined_code) < groq_limit:
            print('under groq_limit')
            print()
            summary_description = groq_summarize_text_description_title_tags(combined_code)
            summary_layers = groq_summarize_text_layers(combined_code)
            print('under groq_limit, summary_layers: ', summary_layers)
            print()
            print('under groq_limit, summary_description: ', summary_description)
            return summary_description, summary_layers
        elif groq_limit < len(combined_code) < OpenAILimit:
            print('under OpenAILimit')
            print()
            summary_description = openai_summarize_text_description_title_tags(combined_code)
            summary_layers = openai_summarize_text_layers(combined_code)
            print('under openAi limit: ', summary_layers, summary_description)
            return summary_description, summary_layers
        elif OpenAILimit < len(combined_code) < chunkLimit:
            print('under chunkLimit')
            print()
            aggregated_summary = summarize_sub_sections(combined_code, 9000)
            summary_description = openai_summarize_text_description_title_tags(aggregated_summary)
            summary_layers = openai_summarize_text_layers(aggregated_summary)
            summary_layers = remove_content_key(summary_layers)
            print()
            print('under chunkLimit: summary_layers ', summary_layers)
            print()
            print('under chunkLimit: summary_description ', summary_description)
            print()
            print('here is the aggregated_summary: ', aggregated_summary)
            print('here is the type of the aggregated summary, ', type(aggregated_summary))
            return summary_description, summary_layers
        else:
            raise ValueError("The combined code exceeds the maximum allowed limit for processing.")
    print('about to go into sizeSplitter')
    surrounding_summary, summary_content = sizeSplitter(file_text)
    print('got passed size splitter')
    summary_content = remove_content_key(summary_content)
    print('got to remove_content_key')

    if not validate_json(json.dumps(surrounding_summary)) or not isinstance(summary_content, list):
        surrounding_summary, summary_content = sizeSplitter(file_text)
        summary_content = remove_content_key(summary_content)

    return surrounding_summary, summary_content

def remove_content_key(summary_content):
    print('got to remove_content_key')
    updated_summary = []
    for item in summary_content:
        # Get the key (e.g., 'abstract', 'methodology', etc.)
        key = list(item.keys())[0]
        # Get the content associated with the key
        content = item[key]['content']
        # Create a new dictionary with the key and its content
        updated_summary.append({key: content})
    print('got to the end of remove content key with updated summary')
    return updated_summary
    
# Route to handle the project file parser request
@pdf_autofill_groq.route('/groqProjectFileParser', methods=['POST', 'OPTIONS'])
@cross_origin()
def projectFileParser():
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'}), 200
    data = request.get_json()
    if not data or 'fileText' not in data:
        return jsonify({'error': 'No fileText provided'}), 400
    file_text = data['fileText']
    try:
        surrounding_summary, summary_content = validate_and_regenerate_json(file_text)
        print()
        print()
        print('projectFileParser: surrounding_summary, ', surrounding_summary)
        print()
        print('projectFileParser: summary_content, ', summary_content)

        return jsonify({'surrounding_summary': surrounding_summary, 'summary_content': summary_content}), 200
    except Exception as e:
        return jsonify({'error': 'Failed to parse proj file'}), 500


