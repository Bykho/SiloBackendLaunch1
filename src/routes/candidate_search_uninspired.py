import os
import io
import json
import PyPDF2
import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from pdfminer.high_level import extract_text as pdfminer_extract
from pdf2image import convert_from_bytes
import pytesseract
import openai
from bson.errors import InvalidId
from bson import ObjectId  # Add this import
from ..search_github_rag import (create_thread, add_message_to_thread, 
                             run_assistant, poll_run_status)
from concurrent.futures import ThreadPoolExecutor, as_completed
from .. import mongo  # Import mongo from your app package

candidate_search_uninspired_bp = Blueprint('candidate_search_uninspired', __name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

openai_api_key = os.getenv('OPENAI_API_KEY')
if not openai_api_key:
    raise EnvironmentError("Missing OPENAI_API_KEY environment variable.")

def extract_text_from_pdf(pdf_file):
    text = ""
    
    try:
        pdf_file.seek(0)
        reader = PyPDF2.PdfReader(pdf_file)
        for page in reader.pages:
            text += page.extract_text() or ""
        if text.strip():
            return text.strip()
    except Exception as e:
        logger.error(f"PyPDF2 extraction failed: {e}")
    
    try:
        pdf_file.seek(0)
        text = pdfminer_extract(io.BytesIO(pdf_file.read()))
        if text.strip():
            return text.strip()
    except Exception as e:
        logger.error(f"pdfminer extraction failed: {e}")
    
    try:
        pdf_file.seek(0)
        images = convert_from_bytes(pdf_file.read())
        for image in images:
            text += pytesseract.image_to_string(image)
        if text.strip():
            return text.strip()
    except Exception as e:
        logger.error(f"OCR extraction failed: {e}")

    raise ValueError("Text extraction failed for all PDF methods.")


def extract_skills(text):
    client = openai.OpenAI()
    prompt = """Extract a list of technical skills from this job description. Return only a JSON array of strings, with no formatting or explanation.

Example:
[
    "Python programming",
    "AWS cloud services",
    "Docker containerization",
    "CI/CD pipelines"
]

Important: Respond ONLY with a JSON array. Do not include any other text, markdown formatting, or explanations.

Job Description:
{text}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You must respond with a valid JSON array of strings only. No other text or formatting."},
                {"role": "user", "content": prompt.format(text=text)}
            ],
            temperature=0.3,
        )
        
        # Log the raw response for debugging
        response_content = response.choices[0].message.content
        logger.info(f"Raw GPT response: {response_content}")

        # Clean up the response
        cleaned_content = response_content.strip()
        if cleaned_content.startswith('```') and cleaned_content.endswith('```'):
            cleaned_content = cleaned_content[3:-3].strip()
        if cleaned_content.startswith('json'):
            cleaned_content = cleaned_content[4:].strip()
            
        logger.info(f"Cleaned content: {cleaned_content}")

        try:
            skills = json.loads(cleaned_content)
            if not isinstance(skills, list):
                logger.error("GPT response is not a list")
                return []
            return skills
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            logger.error(f"Failed content: {cleaned_content}")
            return []

    except Exception as e:
        logger.error(f"Error extracting skills: {e}")
        logger.error(f"Full text being processed: {text[:200]}...")  # Log first 200 chars of input
        return []


def search_github_for_skill(client, skill, assistant_id="asst_hUjlVpcx3CKjAlvmFOgjjsbf"):
    try:
        # Create a separate thread for each skill
        thread_id = create_thread(client, assistant_id)

        # Add the skill as a new message
        add_message_to_thread(client, thread_id, "user", skill)
        run_id = run_assistant(client, thread_id, assistant_id)
        run_output = poll_run_status(client, thread_id, run_id)

        # Get the last assistant message
        _, messages = run_output
        assistant_messages = [msg for msg in messages if msg.role == 'assistant']
        if not assistant_messages:
            return []

        last_message = assistant_messages[-1]
        content = last_message.content[0].text.value if isinstance(last_message.content, list) else last_message.content

        # Extract JSON from within markdown code blocks if present
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0].strip()
        else:
            content = content.strip()

        try:
            data = json.loads(content)
            if 'matches' in data:
                return [m for m in data['matches'] if m.get('score', 0) >= 0.7]
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON response: {e}\nContent was: {content}")
            return []

        return []

    except Exception as e:
        logger.error(f"Error searching GitHub for skill: {e}")
        return []

def is_valid_objectid(id_str: str) -> bool:
    """Check if a string is a valid MongoDB ObjectId."""
    try:
        ObjectId(id_str)
        return True
    except (InvalidId, TypeError):
        return False

@candidate_search_uninspired_bp.route('/JDKeywords', methods=['POST'])
@jwt_required()
def jd_keywords():
    if 'jobDescription' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['jobDescription']
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Invalid file'}), 400

    try:
        text = extract_text_from_pdf(file)
        skills = extract_skills(text)
        if not skills:
            return jsonify({'error': 'Failed to extract skills'}), 500

        client = openai.OpenAI()
        assistant_id = "asst_hUjlVpcx3CKjAlvmFOgjjsbf"

        # Process skills in parallel using ThreadPoolExecutor
        skill_results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_skill = {
                executor.submit(search_github_for_skill, client, skill, assistant_id): skill
                for skill in skills
            }

            for future in as_completed(future_to_skill):
                skill = future_to_skill[future]
                try:
                    matches = future.result()
                except Exception as exc:
                    logger.error(f"{skill} generated an exception: {exc}")
                    matches = []
                skill_results.append({
                    'query': skill,
                    'matches': matches
                })

        # Extract unique user IDs from all matches
        print(f"\n \n \nHere is skill results: {skill_results} \n \n \n")
        user_ids = set()
        for result in skill_results:
            for match in result['matches']:
                file_path = match.get('file_path', '')
                if file_path and '_' in file_path:
                    potential_id = file_path.split('_')[0]
                    if is_valid_objectid(potential_id):  # Only include valid ObjectIds
                        user_ids.add(potential_id)
                        # Add ObjectId to match for later filtering
                        match['user_id'] = potential_id

        # Fetch user information once for all valid users
        user_map = {}
        if user_ids:
            try:
                users = mongo.db.users.find(
                    {'_id': {'$in': [ObjectId(uid) for uid in user_ids]}},
                    {'_id': 1, 'username': 1, 'email': 1, 'github_link': 1}
                )
                
                for user in users:
                    user_map[str(user['_id'])] = {
                        'id': str(user['_id']),
                        'name': user.get('username', ''),
                        'email': user.get('email', ''),
                        'github_link': user.get('github_link', ''),
                        'matches': [],
                        'skills_matched': set(),
                        'total_matches': 0
                    }
            except Exception as e:
                logger.error(f"Error fetching user information: {e}")

        # Only process matches that have valid user IDs
        user_results = {}
        for result in skill_results:
            skill_name = result['query']
            for match in result['matches']:
                if 'user_id' in match and match['user_id'] in user_map:
                    user_id = match['user_id']
                    
                    if user_id not in user_results:
                        user_results[user_id] = user_map[user_id].copy()
                        user_results[user_id]['skills_matched'] = set()
                        user_results[user_id]['total_matches'] = 0
                    
                    match['skill'] = skill_name
                    user_results[user_id]['matches'].append(match)
                    user_results[user_id]['skills_matched'].add(skill_name)
                    user_results[user_id]['total_matches'] += 1

        # Convert to final format
        final_results = {
            'skills_searched': skills,
            'candidates': [
                {
                    **user_data,
                    'skills_matched': list(user_data['skills_matched']),  # Convert set to list
                    'match_score': (len(user_data['skills_matched']) / len(skills)) * 100 if skills else 0
                }
                for user_data in user_results.values()
            ]
        }

        # Sort candidates by match_score in descending order
        final_results['candidates'].sort(key=lambda x: x['match_score'], reverse=True)

        return jsonify(final_results), 200
    
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        return jsonify({'error': str(e)}), 500