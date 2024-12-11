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
from bson import ObjectId
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional
from .. import mongo
from ..search_github_rag import (
    create_thread,
    add_message_to_thread,
    run_assistant,
    poll_run_status,
    attach_vector_store,
    detach_vector_store,
    search_with_retries,
    process_vector_store,
    search_across_stores,
    write_results_to_file
)

# Configure Blueprint and logging
candidate_search_uninspired_bp = Blueprint('candidate_search_uninspired', __name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Validate environment variables
openai_api_key = os.getenv('OPENAI_API_KEY')
if not openai_api_key:
    raise EnvironmentError("Missing OPENAI_API_KEY environment variable.")

def extract_text_from_pdf(pdf_file) -> str:
    """Extract text from PDF using multiple methods with fallback."""
    text = ""
    
    # Try PyPDF2 first
    try:
        pdf_file.seek(0)
        reader = PyPDF2.PdfReader(pdf_file)
        for page in reader.pages:
            text += page.extract_text() or ""
        if text.strip():
            return text.strip()
    except Exception as e:
        logger.error(f"PyPDF2 extraction failed: {e}")
    
    # Try pdfminer if PyPDF2 fails
    try:
        pdf_file.seek(0)
        text = pdfminer_extract(io.BytesIO(pdf_file.read()))
        if text.strip():
            return text.strip()
    except Exception as e:
        logger.error(f"pdfminer extraction failed: {e}")
    
    # Try OCR as last resort
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

def extract_skills(text: str) -> List[str]:
    """Extract technical skills from job description text using GPT-4."""
    client = openai.OpenAI()
    
    prompt = """Extract a list of technical skills from this job description. Return only a JSON array of strings, with no formatting or explanation. They should be longer sentences that would work well as a query for a vector store of code files.

Example:
[
    "Experience with python programming",
    "Past work implementing AWS cloud services",
    "Experience with Docker containerization",
]

Important: Respond ONLY with a JSON array. Do not include any other text, markdown formatting, or explanations.

Job Description:
{text}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You must respond with a valid JSON array of strings only. No other text or formatting."},
                {"role": "user", "content": prompt.format(text=text)}
            ],
            temperature=0.3,
        )
        
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
        logger.error(f"Full text being processed: {text[:200]}...")
        return []

def fetch_user_details(db, user_ids: List[str]) -> Dict:
    """Fetch user details from MongoDB."""
    try:
        users = db.users.find(
            {'_id': {'$in': [ObjectId(uid) for uid in user_ids]}},
            {'_id': 1, 'username': 1, 'email': 1, 'github_link': 1}
        )
        
        return {
            str(user['_id']): {
                'id': str(user['_id']),
                'name': user.get('username', ''),
                'email': user.get('email', ''),
                'github_link': user.get('github_link', ''),
                'matches': [],
                'skills_matched': set(),
                'total_matches': 0
            }
            for user in users
        }
    except Exception as e:
        logger.error(f"Error fetching user details: {e}")
        return {}

def format_results(user_map: Dict, skill_results: Dict, total_skills: int) -> Dict:
    """Format the final results with user details and match scores."""
    for user_id, results in skill_results.items():
        if user_id in user_map:
            user_data = user_map[user_id]
            user_data['matches'].extend(results['matches'])
            user_data['skills_matched'].update(results['skills_matched'])
            user_data['total_matches'] = len(results['matches'])

    candidates = [
        {
            'id': user_data['id'],
            'name': user_data['name'],
            'email': user_data['email'],
            'github_link': user_data['github_link'],
            'skills_matched': list(user_data['skills_matched']),
            'match_score': (len(user_data['skills_matched']) / total_skills * 100) if total_skills else 0,
            'matches': user_data['matches']
        }
        for user_data in user_map.values()
    ]

    candidates.sort(key=lambda x: x['match_score'], reverse=True)
    return candidates

@candidate_search_uninspired_bp.route('/JDKeywords', methods=['POST'])
@jwt_required()
def jd_keywords():
    """Process job description and search for matching candidates."""
    if 'jobDescription' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['jobDescription']
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Invalid file type. Please provide a PDF file.'}), 400

    try:
        # Extract text and skills from PDF
        text = extract_text_from_pdf(file)
        skills = extract_skills(text)
        if not skills:
            return jsonify({'error': 'No skills could be extracted from the document'}), 500

        client = openai.OpenAI()
        assistant_id = "asst_hUjlVpcx3CKjAlvmFOgjjsbf"

        # Fetch active vector stores
        vector_stores = [
            {
                "user_id": str(store["user_id"]),
                "vectorstore_idx": store["vectorstore_idx"]
            }
            for store in mongo.db.vector_stores.find({"status": "active"})
        ]

        print(f'\n \n Here are the vector stores: {vector_stores} \n \n ')

        if not vector_stores:
            return jsonify({'error': 'No active vector stores available'}), 500

        # Search across all vector stores
        skill_results = search_across_stores(
            client=client,
            assistant_id=assistant_id,
            vector_stores=vector_stores,
            skills=skills
        )

        if not skill_results:
            return jsonify({
                'skills_searched': skills,
                'candidates': []
            }), 200

        # Fetch and format user details
        user_map = fetch_user_details(mongo.db, list(skill_results.keys()))
        candidates = format_results(user_map, skill_results, len(skills))

        # Prepare final response
        final_results = {
            'skills_searched': skills,
            'candidates': candidates
        }

        # Save results to file
        summary = text[:100] + "..." if len(text) > 100 else text
        try:
            output_file = write_results_to_file(summary, final_results)
            logger.info(f"Results saved to: {output_file}")
        except Exception as e:
            logger.error(f"Error saving results to file: {e}")

        return jsonify(final_results), 200

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        return jsonify({'error': 'An error occurred processing your request'}), 500