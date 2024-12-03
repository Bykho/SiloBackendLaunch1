# candidate_search_uninspired.py

import os
import io
import re
import json
import openai
import PyPDF2
import time
import requests
from flask import Blueprint, request, jsonify, current_app
from .. import mongo  # Ensure 'mongo' is correctly set up in your main application
from pdfminer.high_level import extract_text as pdfminer_extract
from pdf2image import convert_from_bytes
from PIL import Image
import pytesseract
from flask_jwt_extended import jwt_required

# Initialize Blueprint
candidate_search_uninspired_bp = Blueprint('candidate_search_uninspired', __name__)

# Set OpenAI API key
openai.api_key = os.environ.get('OPENAI_API_KEY')

# Set GitHub Token for authenticated requests (to increase rate limits)
GITHUB_TOKEN = os.environ.get('GITHUB_API_TOKEN')


def extract_text_from_pdf(pdf_file):
    """
    Extract text from a PDF file using multiple methods.
    
    Returns:
        str: Extracted text from the PDF.
    """
    text = ""
    
    # Method 1: PyPDF2 (for PDFs with embedded text)
    try:
        pdf_file.seek(0)
        reader = PyPDF2.PdfReader(pdf_file)
        for page in reader.pages:
            page_text = page.extract_text() or ""
            text += page_text
        if text.strip():
            return text.strip()
    except Exception as e:
        print(f"PyPDF2 extraction failed: {e}")
    
    # Method 2: pdfminer (for more complex PDFs with embedded text)
    try:
        pdf_file.seek(0)
        text = pdfminer_extract(io.BytesIO(pdf_file.read()))
        if text.strip():
            return text.strip()
    except Exception as e:
        print(f"pdfminer extraction failed: {e}")
    
    # Method 3: OCR with Tesseract (for scanned PDFs or images)
    if not text.strip():
        try:
            pdf_file.seek(0)
            images = convert_from_bytes(pdf_file.read())
            for image in images:
                ocr_text = pytesseract.image_to_string(image)
                text += ocr_text
            if text.strip():
                return text.strip()
        except Exception as e:
            print(f"OCR extraction failed: {e}")

    raise ValueError("Text extraction failed for all PDF methods.")


def extract_technical_descriptions(text):
    print('\n \n \n \n extract_technical_descriptions \n \n \n \n')
    """
    Extract all technical descriptions, skills, technologies, and qualifications from the provided job description using OpenAI.
    
    Returns:
        str: A string containing all relevant technical descriptions.
    """
    prompt = f"""
    You are an AI assistant specialized in analyzing job descriptions to extract sections related to technical skills, technologies, and qualifications.
    Your task is to process the following job description and extract all relevant technical sections or paragraphs. Exclude any sections that pertain to non-technical aspects such as healthcare offerings, general company benefits, or unrelated information.
    
    **Job Description:**
    {text}
    
    **Instructions:**
    - Identify and extract all sections or paragraphs that detail technical skills, technologies, tools, programming languages, frameworks, methodologies, and qualifications required for the role.
    - Preserve the original context and formatting of the extracted sections or paragraphs.
    - Exclude any non-technical sections such as those related to healthcare benefits, company culture, or general job perks.
    - Present the extracted technical sections as a single block of text, maintaining paragraph separations.
    
    """
    print('Here is the prompt for extracting technical descriptions:', prompt)
    try:
        response = openai.ChatCompletion.create(
            messages=[
                {"role": "system", "content": "You extract relevant technical skills and descriptions based on provided content."},
                {"role": "user", "content": prompt}
            ],
            model="gpt-4o",  # Corrected model name
            max_tokens=3000,  # Adjusted as needed
            temperature=0.3,  # Low temperature for consistency
        )
        
        # Extract and clean the response content
        technical_output = response.choices[0].message['content'].strip()
        
        print(f'\n\n here is the technical output: {technical_output} \n \n')

        # Remove any Markdown formatting if present
        technical_output = re.sub(r'(^```json|```$)', '', technical_output).strip()
        technical_output = technical_output.replace("```", "").strip()
        
        print('Here are the extracted technical descriptions:', technical_output)
        
        return technical_output
    
    except Exception as e:
        print(f"Error extracting technical descriptions: {e}")
        return ""


def generate_keywords_from_text(technical_text):
    print('\n\n\n generate_keywords_from_text \n\n\n')
    print(f'Here is the extracted text we are working with: {technical_text}\n\n')

    prompt = f"""
    You are an AI assistant specialized in analyzing technical descriptions to extract key skills, technologies, and qualifications.
    Your task is to process the following technical information and provide a detailed JSON array containing multiple objects with:

    1. **ImportantSkill**: Identify the most critical and specific skills or areas of expertise required for this role. Each should be a high-level skill directly relevant to the job responsibilities, such as "Cloud Native Software Development," "DevOps Practices," etc.

    2. **Keywords**: For each "ImportantSkill," generate a comprehensive list of **exactly 35 technical keywords or key phrases** that are specifically related to that skill. These keywords should be **code-specific indicators** that demonstrate proficiency in the skill, such as programming constructs, specific libraries, frameworks, functions, or design patterns.

    **Guidelines:**
    - **Relevance**: All keywords must be directly related to their corresponding "ImportantSkill" and the overall technical descriptions.
    - **Code-Specificity**: Keywords should include code constructs, specific libraries/frameworks, functions, classes, or design patterns that indicate hands-on experience.
    - **Format**: The output must be a JSON array of objects. Each object should have exactly two keys: "ImportantSkill" and "Keywords." Do not include any additional keys, explanations, or text outside of this JSON structure.
    - **Validation**: Ensure that the JSON is well-formed and free of syntax errors.

    **Technical Descriptions:**
    {technical_text}

    **Example Output:**
    [
        {{
            "ImportantSkill": "Cloud Native Software Development",
            "Keywords": [
                "Kubernetes",
                "Helm",
                "gRPC",
                "REST",
                "Lambda",
                "Terraform",
                "GKE",
                "CircleCI",
                "GitOps",
                "Prometheus",
                "Fluentd"
            ]
        }},
        {{
            "ImportantSkill": "DevOps Practices",
            "Keywords": [
                "Ansible",
                "Puppet",
                "Chef",
                "Nagios",
                "Bitbucket",
                "GitLab",
                "Terraform",
                "AWS",
                "Azure",
                "GCP",
            ]
        }}
    ]

    **Instructions:**
    - Analyze the technical descriptions thoroughly to identify multiple pivotal skills.
    - For each identified "ImportantSkill," develop a precise list of 35 code-specific keywords that comprehensively cover all technical aspects related to that skill.
    - Ensure the final output strictly adheres to the JSON array format as illustrated in the example.
    - Do not provide any additional commentary, explanations, or markdown formatting outside the JSON array.
    
    THE KEYWORDS SHOULD BE WORDS THAT YOU WOULD SEE IN A CODE FILE. NOT TOPICS. BUT KEYWORDS THAT SHOULD EXIST IN A CODE FILE FOR SOMEONE WHO IS PROFICIENT AT THE "IMPORTANT SKILL".
    THIS COULD BE ESSENTIAL LIBRARIES THAT ARE ASSOCIATED WITH THAT SKILL OR MAYBE COMMON SYNTAX THAT ARE USED IN THAT SKILL.
    ENSURE THAT ALL THE KEYWORDS ARE THINGS YOU WOULD FIND IN A CODE FILE. NOT GENERAL THINGS LIKE, FOR EXAMPLE, "CLOUD STORAGE".
    """
    print('Here is the updated prompt for generating multiple skills and keywords:', prompt)

    try:
        response = openai.ChatCompletion.create(
            messages=[{"role": "system", "content": "You extract relevant skills and code-specific keywords based on provided content."},
                      {"role": "user", "content": prompt}],
            model="gpt-4o",
            max_tokens=1500,
            temperature=0.3,
        )
        
        raw_output = response.choices[0].message['content'].strip()
        print('Raw OpenAI Response:', raw_output)

        # Clean up the response by removing any backticks and the `json` language tag
        if raw_output.startswith("```json"):
            raw_output = raw_output[7:]  # Remove the opening ```json
        if raw_output.endswith("```"):
            raw_output = raw_output[:-3]  # Remove the closing ```

        # Further strip whitespace to ensure clean JSON
        raw_output = raw_output.strip()

        # Parse the cleaned output as JSON
        keywords_list = json.loads(raw_output)
        
        print('Generated list of skills and keywords:', keywords_list)

        return keywords_list

    except json.JSONDecodeError as json_error:
        print("JSON decoding failed. Output was not valid JSON:", raw_output)
        print("JSON Error:", json_error)
        return []
    except Exception as e:
        print(f"Error generating keywords: {e}")
        return []




@candidate_search_uninspired_bp.route('/JDKeywords', methods=['POST'])
@jwt_required()
def jd_keywords():
    """
    Handle the /JDKeywords route to extract ImportantSkills and Keywords from a job description PDF.
    """
    print('\n\nOpened the JDKeywords route\n')

    # Check if the file is in the request
    if 'jobDescription' not in request.files:
        print("No file named 'jobDescription' found in request files.")
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['jobDescription']
    
    # Check if the filename is empty
    if file.filename == '':
        print("File name is empty.")
        return jsonify({'error': 'No file selected'}), 400
    
    # Check if the file is a PDF
    if not file.filename.lower().endswith('.pdf'):
        print("File is not a PDF.")
        return jsonify({'error': 'Only PDF files are allowed'}), 400
    
    try:
        # Extract text from PDF
        text = extract_text_from_pdf(file)
        
        if not text:
            print("Text extraction failed or file is empty.")
            return jsonify({'error': 'Failed to extract text from the file or file is empty'}), 400
        
        # Layer 1: Extract technical descriptions
        technical_text = extract_technical_descriptions(text)
        
        if not technical_text:
            print("Technical descriptions extraction failed.")
            return jsonify({'error': 'Failed to extract technical descriptions from document'}), 500
        
        # Layer 2: Generate keywords from technical descriptions
        keywords_list = generate_keywords_from_text(technical_text)
        
        if not keywords_list:
            print("Keyword generation failed.")
            return jsonify({'error': 'Failed to generate keywords from technical descriptions'}), 500

        print("Keyword generation successful.")
        return jsonify(keywords_list), 200  # Return the list directly
    
    except ValueError as ve:
        print(f"ValueError encountered: {ve}")
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        print(f"Unexpected error encountered: {e}")
        return jsonify({'error': 'Internal server error'}), 500










def extract_github_username(github_link):
    """
    Extract GitHub username from a given GitHub URL or username string.
    """
    pattern = r'(?:https?://)?(?:www\.)?github\.com/([^/]+)/?'
    match = re.search(pattern, github_link)
    if match:
        return match.group(1)
    else:
        # If github_link is just the username
        return github_link.strip('/')


def search_github_repos_for_keywords(github_username, keywords):
    """
    Search the user's public GitHub repositories for each keyword and count the occurrences.

    Args:
        github_username (str): The GitHub username.
        keywords (list): List of keywords to search for.

    Returns:
        dict: A dictionary with keywords as keys and their respective counts as values.
    """
    keyword_counts = {keyword: 0 for keyword in keywords}

    headers = {
        'Accept': 'application/vnd.github.v3+json'
    }
    if GITHUB_TOKEN:
        headers['Authorization'] = f'token {GITHUB_TOKEN}'
    else:
        print("Warning: No GitHub token found. Rate limits may apply.")
        # The Code Search API requires authentication
        return keyword_counts

    for keyword in keywords:
        # Construct the search query
        # Search code for the keyword within the user's repositories
        query = f'{keyword} user:{github_username} in:file'

        search_url = 'https://api.github.com/search/code'
        params = {'q': query, 'per_page': 1}  # We only need total_count

        try:
            response = requests.get(search_url, headers=headers, params=params)
            
            # Handle rate limiting
            if response.status_code == 403:
                if 'X-RateLimit-Remaining' in response.headers and response.headers['X-RateLimit-Remaining'] == '0':
                    reset_time = int(response.headers.get('X-RateLimit-Reset', time.time()))
                    sleep_time = max(reset_time - time.time(), 1)
                    print(f"Rate limit exceeded. Sleeping for {sleep_time} seconds.")
                    time.sleep(sleep_time)
                    response = requests.get(search_url, headers=headers, params=params)
                else:
                    print(f"Access forbidden when searching for keyword '{keyword}'.")
                    continue

            if response.status_code != 200:
                print(f"Failed to search code for user '{github_username}' and keyword '{keyword}'. Status Code: {response.status_code}")
                continue

            search_results = response.json()
            total_count = search_results.get('total_count', 0)
            keyword_counts[keyword] = total_count

            # Sleep briefly to avoid hitting rate limits (adjust as needed)
            time.sleep(1)

        except requests.exceptions.RequestException as e:
            print(f"RequestException occurred while searching for keyword '{keyword}': {e}")
            continue

    return keyword_counts


@candidate_search_uninspired_bp.route('/candidate_search_uninspired', methods=['POST'])
@jwt_required()
def candidate_search():
    """
    Handle the /candidate_search_uninspired route to search for candidates based on keywords.
    """
    # Get the keywords from the request
    data = request.get_json()
    if not data or 'Keywords' not in data:
        return jsonify({'error': 'No keywords provided'}), 400

    keywords = data['Keywords']
    print(f"Received keywords: {keywords}")

    # Connect to MongoDB and get users with a GitHub link or GitHub in personal_website
    users_collection = mongo.db['users']  # Adjust collection name as needed

    # Filter: users with a filled 'github_link' or 'personal_website' containing 'github.com'
    users_with_github = users_collection.find({
        '$or': [
            {'github_link': {'$exists': True, '$ne': ''}},
            {'personal_website': {'$regex': 'github\\.com', '$options': 'i'}}
        ]
    })
    candidates = []

    # For each user, get their GitHub username and search for keywords
    for user in users_with_github:
        github_link = user.get('github_link')
        if not github_link:
            personal_website = user.get('personal_website', '')
            if 'github.com' in personal_website.lower():
                github_link = personal_website
            else:
                continue  # Skip if no GitHub link is found

        github_username = extract_github_username(github_link)
        if not github_username:
            continue  # Skip if GitHub username extraction fails

        # Search for keywords in user's GitHub repositories
        keyword_counts = search_github_repos_for_keywords(github_username, keywords)

        candidates.append({
            'username': user.get('username'),
            'github_link': github_link,
            'keyword_counts': keyword_counts,
        })

    # Return the candidates data
    return jsonify(candidates), 200