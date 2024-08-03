


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

# Summarizes the text to get a description, tags, and name for the project
# Calls: remove_trailing_commas
def summarize_text_description_title_tags(text):
    try:
        print('Got to summarize_text_description_title_tags')
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

# Summarizes the text into detailed sections like abstract, methodology, future work, results
# Calls: remove_trailing_commas
def summarize_text_layers(text):
    print()
    print()
    print()
    print("summarize_text_layers: here is the text going in: ", text)
    print()
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

# Attempts to load a JSON string and return it in a valid format
def validate_and_correct_json(json_str):
    try:
        json_obj = json.loads(json_str)
        return json.dumps(json_obj)
    except json.JSONDecodeError:
        return '{}'

# Splits text into chunks of a specified size
def split_into_chunks(text, chunk_size):
    # Logic to split text into logical chunks, ensuring coherence
    chunks = []
    while text:
        chunk = text[:chunk_size]
        text = text[chunk_size:]
        chunks.append(chunk)
    return chunks

# Summarizes a sub-section of text using the OpenAI API
def summarize_sub_section(sub_section):
    # Summarize the sub-section using the OpenAI API
    print('summarize_sub_section')
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Please summarize the following content and keep it short but relevant. Keep it to be around ."},
                {"role": "user", "content": f"{sub_section}"}
            ],
            max_tokens=600,
            temperature=0.2
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        print(f"Error summarizing sub-section: {e}")
        return ""


# Splits the text into sub-sections, summarizes each sub-section in parallel, and aggregates the summaries
# Calls: split_into_chunks, summarize_sub_section
def summarize_sub_sections(text, chunk_size=9000):
    # Split the text into sub-sections
    sub_sections = split_into_chunks(text, chunk_size)
    
    # Summarize each sub-section in parallel
    with concurrent.futures.ThreadPoolExecutor() as executor:
        summarized_sub_sections = list(executor.map(summarize_sub_section, sub_sections))
    
    # Aggregate the summarized sub-sections
    aggregated_summary = ' '.join(summarized_sub_sections)
    
    return aggregated_summary



# Validates and regenerates JSON by summarizing the text and running the existing summarization functions
# Calls: summarize_sub_sections, summarize_text_description_title_tags, summarize_text_layers, validate_json
def validate_and_regenerate_json(file_text, chunk_threshold=9001):
    # Summarize the large text document into sub-sections if it exceeds the threshold
    print('validate_and_regenerate_json: made it into validate_and_regenerate_json')
    if len(file_text) > chunk_threshold:
        print('validate_and_regenerate_json: chunking the text')
        aggregated_summary = summarize_sub_sections(file_text)
    else:
        aggregated_summary = file_text

    # Run existing summarization functions on the aggregated summary in parallel
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_surrounding_summary = executor.submit(summarize_text_description_title_tags, aggregated_summary)
        future_summary_content = executor.submit(summarize_text_layers, aggregated_summary)
        
        surrounding_summary = future_surrounding_summary.result()
        summary_content = future_summary_content.result()

    if not validate_json(json.dumps(surrounding_summary)):
        print("Invalid JSON for surrounding_summary, regenerating...")
        surrounding_summary = summarize_text_description_title_tags(aggregated_summary)

    if not validate_json(json.dumps(summary_content)):
        print("Invalid JSON for summary_content, regenerating...")
        summary_content = summarize_text_layers(aggregated_summary)

    return surrounding_summary, summary_content


# Route to handle the project file parser request
# Calls: validate_and_regenerate_json
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


