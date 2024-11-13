# candidate_search.py

import os
import io
import re
import json
import openai
import pinecone
import PyPDF4
import pytesseract
import pdfminer
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from pymongo import MongoClient
from pdfminer.high_level import extract_text as pdfminer_extract
from PIL import Image
from pdf2image import convert_from_bytes
from bson import ObjectId
from ..routes.pinecone_utils import initialize_pinecone, query_similar_vectors, query_similar_vectors_users  # Adjust import paths as necessary
import base64

candidate_search_bp = Blueprint('candidate_search', __name__)

openai.api_key = os.environ.get('OPENAI_API_KEY')

pinecone_index = initialize_pinecone()


# Initialize MongoDB
MONGO_URI = os.environ.get('MONGO_URI')
mongo_client = MongoClient(MONGO_URI)
db = mongo_client['ProductionDatabase']  # Replace with your actual database name
candidates_collection = db['users']  # Replace with your actual candidates collection name



def extract_text_from_pdf(pdf_file):
    """
    Extract text from a PDF file using multiple methods.
    """
    text = ""
    
    # Method 1: PyPDF4 (for PDFs with embedded text)
    try:
        pdf_file.seek(0)
        reader = PyPDF4.PdfFileReader(pdf_file)
        for page in range(reader.numPages):
            text += reader.getPage(page).extractText() or ""
        if text.strip() and is_text_valid(text):
            return text.strip()
    except Exception as e:
        print(f"PyPDF4 extraction failed: {e}")
    
    # Method 2: pdfminer (for more complex PDFs with embedded text)
    try:
        pdf_file.seek(0)
        text = pdfminer_extract(io.BytesIO(pdf_file.read()))
        
        if text.strip() and is_text_valid(text):
            return text.strip()
    except Exception as e:
        print(f"pdfminer extraction failed: {e}")
    
    # Method 3: OCR with Tesseract (for scanned PDFs or images)
    if not is_text_valid(text):
        try:
            pdf_file.seek(0)
            images = convert_from_bytes(pdf_file.read())
            for image in images:
                text += pytesseract.image_to_string(image)
            
            if text.strip():
                return text.strip()
        except Exception as e:
            print(f"OCR extraction failed: {e}")

    raise ValueError("Text extraction failed for all PDF methods.")


def is_text_valid(extracted_text):
    return (
        not is_text_garbled(extracted_text) and
        has_reasonable_word_length(extracted_text)
    )


def is_text_garbled(extracted_text):
    non_alnum_count = sum(1 for char in extracted_text if not char.isalnum())
    total_char_count = len(extracted_text)
    
    if total_char_count == 0:
        return True  # Empty text is considered garbled
    
    non_alnum_ratio = non_alnum_count / total_char_count
    
    # If more than 40% of the text is non-alphanumeric, consider it garbled
    return non_alnum_ratio > 0.4


def has_reasonable_word_length(extracted_text, min_average_length=3):
    words = extracted_text.split()
    if not words:
        return False  # No words, likely garbled
    
    average_word_length = sum(len(word) for word in words) / len(words)
    
    # If the average word length is below 3 characters, consider it garbled
    return average_word_length >= min_average_length


def generate_keywords(job_description_text):
    """
    Generate relevant keywords from the job description using OpenAI's GPT-4.
    Returns a list of keywords.
    """
    print("JOB DESCRIPTION TEXT:", job_description_text)
    prompt = f"""
    You are an AI assistant that extracts key skills, technologies, and qualifications from a job description.
    Analyze the following job description and provide a JSON array of relevant keywords or key phrases that can effectively match candidate profile attributes.
    Focus on technical skills, technologies, programming languages, methodologies, and other relevant qualifications.
    YOU MUST FOCUS ON THE FOLLOWING:
    1) Key words relating to the specific tech stack mentioned in the job description
    2) Location if it is mentioned in the job description
    3) Engineering frameworks necessary here
    4) Technical skills
    5) Other relevant technical keywords.
    
    Job Description:
    {job_description_text}

    Provide only a JSON array of strings representing the keywords. Do not include any additional text.
    """

    try:
        response = openai.ChatCompletion.create(
            messages=[
                {
                    "role": "system", 
                    "content": "You extract relevant keywords based on job descriptions."
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            model="gpt-4",  # Ensure the model name is correct
            max_tokens=500,
            temperature=0.3,
        )
        
        # Print full response for debugging
        #print("Full OpenAI Response:", response)

        # Extract the keyword content, removing any enclosing code block formatting
        keyword_output = response.choices[0].message['content'].strip()
        print("Keyword Output Content Before Cleanup:", keyword_output)

        # Remove any leading and trailing ```json or ``` characters
        keyword_output = re.sub(r'(^```json|```$)', '', keyword_output).strip()

        # Remove any remaining code block backticks
        keyword_output = keyword_output.replace("```", "").strip()

        # Try to parse the cleaned-up output as JSON
        keywords = json.loads(keyword_output)
        if not isinstance(keywords, list):
            raise ValueError("Expected a JSON array of keywords.")
        
        return keywords

    except json.JSONDecodeError as json_error:
        print("JSON decoding failed. Output was not valid JSON:", keyword_output)
        print("JSON Error:", json_error)
        return []
    except Exception as e:
        print(f"Error generating keywords: {e}")
        return []


def generate_embedding(text):
    """
    Generate embedding for the given text using OpenAI's Ada model.
    """
    try:
        response = openai.Embedding.create(
            input=text,
            model="text-embedding-ada-002"  # Use the appropriate embedding model
        )
        embedding = response['data'][0]['embedding']
        return embedding
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return None

def perform_keyword_search(keywords):
    try:
        results = []
        
        # Define the fields to search
        fields_to_search = ["skills", "technologies", "qualifications", "biography"]
        
        # Construct $or query with $regex for each keyword and field
        or_conditions = []
        for keyword in keywords:
            for field in fields_to_search:
                or_conditions.append({field: {"$regex": re.escape(keyword), "$options": "i"}})
        
        query = {"$or": or_conditions}
        
        # Search the 'users' collection
        users = candidates_collection.find(query)
        for user in users:
            user['_id'] = str(user['_id'])
            results.append(user)
            print(f"Keyword User match: {user['username']}")
        
        # Search the 'projects' collection
        projects = db['projects'].find(query)
        for project in projects:
            project['_id'] = str(project['_id'])
            results.append(project)
            print(f"Keyword Project match: {project.get('name', 'N/A')}")
        
        return results
    except Exception as e:
        print(f"Error performing keyword search: {e}")
        return []


def DB_retrieval_from_vector(metadata):
    """
    Retrieve specific user profile information from MongoDB based on embedding metadata.

    Parameters:
        metadata (dict): The metadata dictionary extracted from Pinecone embedding results.
                         Expected keys: 'user_id', 'type', 'project_id' (optional for portfolio entries).

    Returns:
        dict: The retrieved user profile information corresponding to the embedding type.
              Returns an empty dictionary if no matching data is found.
    """
    try:
        user_id = metadata.get('user_id')
        embedding_type = metadata.get('type')
        project_id = metadata.get('project_id', None)

        if not user_id or not embedding_type:
            print("Metadata is missing 'user_id' or 'type'.")
            return {}

        if embedding_type == 'full user':
            # Retrieve the full user profile from 'users' collection
            user_data = candidates_collection.find_one({'_id': ObjectId(user_id)})
            if not user_data:
                print(f"No user found with user_id: {user_id}")
                return {}
            return user_data

        elif embedding_type == 'resume':
            # Retrieve the 'resume' field from the user document
            user_data = candidates_collection.find_one(
                {'_id': ObjectId(user_id)},
                {'resume': 1, 'username': 1, 'email': 1}
            )
            if not user_data:
                print(f"No user found with user_id: {user_id}")
                return {}
            return user_data

        elif embedding_type == 'work experience':
            # Retrieve the 'workhistory' field from the user document
            user_data = candidates_collection.find_one(
                {'_id': ObjectId(user_id)},
                {'workhistory': 1, 'username': 1, 'email': 1}
            )
            if not user_data:
                print(f"No user found with user_id: {user_id}")
                return {}
            return user_data

        elif embedding_type == 'portfolio entry':
            # Retrieve the project from 'projects' collection using 'project_id'
            if not project_id:
                print("Metadata is missing 'project_id' for portfolio entry.")
                return {}
            project_data = db['projects'].find_one({'_id': ObjectId(project_id)})
            if not project_data:
                print(f"No project found with project_id: {project_id}")
                return {}
            return project_data

        else:
            print(f"Unknown embedding type: {embedding_type}")
            return {}

    except Exception as e:
        print(f"Error retrieving data from DB: {e}")
        return {}


def perform_embedding_search(job_embedding, top_k=5):
    """
    Perform semantic search using embeddings and Pinecone, retrieving additional data from MongoDB based on metadata.
    """
    try:
        # Query Pinecone index
        print('\n \n checking out similar vectors \n \n')
        results = query_similar_vectors(pinecone_index, job_embedding, top_k=top_k)
        
        # Extract metadata and additional information from MongoDB for each result
        candidates = []
        for match in results:
            if match['id'] == "temp_job_description":
                continue  # Skip the temporary job description embedding
            
            metadata = match.get('metadata', {})
            print(f"Found Embedding. Type: {metadata.get('type', 'N/A')}, Username: {metadata.get('username', 'N/A')}")
            print(f"here is all the metadata: {metadata} \n")
            
            # Retrieve additional details from MongoDB based on metadata
            candidate_data = DB_retrieval_from_vector(metadata)
            if not candidate_data:
                continue  # Skip if no data found
            
            # Attach score and add to candidates list
            candidate_data['embedding_score'] = match['score']
            candidates.append(candidate_data)
            print(f"Embedding Candidate match: {candidate_data.get('_id', 'N/A')}")
        
        return candidates
    except Exception as e:
        print(f"Error performing embedding search: {e}")
        return []



def combine_search_results(keyword_results, embedding_results):
    """
    Combine keyword and embedding search results using an ensemble method.
    Assign scores based on both keyword matches and embedding similarity.
    """
    combined_scores = {}
    explanations = {}
    
    # Assign keyword scores
    for candidate in keyword_results:
        cid = candidate['_id']
        combined_scores[cid] = combined_scores.get(cid, 0) + 1  # +1 for each keyword match
        explanations[cid] = explanations.get(cid, []) + ['Keyword Match']
    
    # Print out all input scores associated with candidates from keyword results
    print("Keyword Scores:")
    for cid, score in combined_scores.items():
        print(f"Candidate ID: {cid}, Keyword Score: {score}")
    
    # Assign embedding scores (normalized)
    if embedding_results:
        max_embedding_score = max([c['embedding_score'] for c in embedding_results], default=1)
        for candidate in embedding_results:
            cid = candidate['_id']
            normalized_score = candidate['embedding_score'] / max_embedding_score  # Normalize between 0 and 1
            combined_scores[cid] = combined_scores.get(cid, 0) + normalized_score
            explanations[cid] = explanations.get(cid, []) + [f"Embedding Score: {normalized_score:.2f}"]
        
        # Print out all input scores associated with candidates from embedding results
        print("Embedding Scores:")
        for candidate in embedding_results:
            cid = candidate['_id']
            print(f"Candidate ID: {cid}, Embedding Score: {candidate['embedding_score']:.2f}")
    else:
        print("No embedding results to score.")
    
    # Combine candidates
    all_candidate_ids = set(combined_scores.keys())
    combined_candidates = []
    for cid in all_candidate_ids:
        candidate_data = candidates_collection.find_one({'_id': ObjectId(cid)}) if ObjectId.is_valid(cid) else None
        if candidate_data:
            candidate = {
                'id': cid,
                'username': candidate_data.get('username', 'N/A'),
                'skills': candidate_data.get('skills', []),
                'technologies': candidate_data.get('technologies', []),
                'qualifications': candidate_data.get('qualifications', []),
                'final_score': combined_scores[cid],
                'explanations': explanations[cid],
            }
            combined_candidates.append(candidate)
    
    # Sort candidates by final_score descending
    combined_candidates = sorted(combined_candidates, key=lambda x: x['final_score'], reverse=True)
    
    return combined_candidates


def generate_explanation(candidate, job_description_text):
    """
    Generate a natural language explanation for why a candidate is a good fit.
    """
    print('\n running generate explanation on: ', candidate)
    try:
        explanation_prompt = f"""
        Generate a brief explanation for why the following candidate is a good fit for the job description based on their skills, technologies, qualifications, and the provided scores.

        Job Description:
        {job_description_text}

        Candidate Details:
        Username: {candidate['username']}
        Skills: {', '.join(candidate['skills'])}
        Technologies: {', '.join(candidate['technologies'])}
        Qualifications: {', '.join(candidate['qualifications'])}
        Explanations: {', '.join(candidate['explanations'])}

        Explanation:
        """
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": explanation_prompt}
            ],
            max_tokens=500,
            temperature=0.3,
        )
        print('response: ', response)
        explanation = response.choices[0].message['content'].strip()
        print('explanation: ', explanation)
        return explanation
    except Exception as e:
        print(f"Error generating explanation: {e}")
        return "Explanation not available."



@candidate_search_bp.route('/candidateSearch', methods=['POST'])
@jwt_required()
def candidate_search():
    if 'jobDescription' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['jobDescription']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Only PDF files are allowed'}), 400
    
    try:
        # Extract text from PDF
        text = extract_text_from_pdf(file)
        
        if not text:
            return jsonify({'error': 'Failed to extract text from the file or file is empty'}), 400
        
        # Generate keywords using LLM
        keywords = generate_keywords(text)
        #print(f"Generated Keywords: {keywords}")
        
        if not keywords:
            return jsonify({'error': 'Failed to generate keywords from job description'}), 500
        
        # Perform keyword-based search
        keyword_search_results = perform_keyword_search(keywords)
        print(f"Keyword Search Results Count: {len(keyword_search_results)}")
        
        # Generate embedding for the job description
        job_embedding = generate_embedding(text)
        if not job_embedding:
            return jsonify({'error': 'Failed to generate embedding for job description'}), 500
        
        # Temporarily upsert the job embedding to Pinecone
        temp_job_id = "temp_job_description"  # Unique ID for temporary embedding
        pinecone_index.upsert([(temp_job_id, job_embedding, {"type": "temp_job"})])
    
        # Perform embedding-based search
        embedding_search_results = perform_embedding_search(job_embedding, top_k=50)
        print(f"Embedding Search Results Count: {len(embedding_search_results)}")
        
        # Delete the temporary embedding after search
        pinecone_index.delete(ids=[temp_job_id])
    
        # Combine the search results using ensemble method
        combined_candidates = combine_search_results(keyword_search_results, embedding_search_results)
        print(f"Combined Candidates Count: {len(combined_candidates)}")
        
        # Generate explanations for top candidates (e.g., top 10)
        top_candidates = combined_candidates[:3]
        for candidate in top_candidates:
            holder_explanation = generate_explanation(candidate, text)
            print('holder explanation: ', holder_explanation)
            candidate['explanation'] = holder_explanation

        return jsonify({'results': top_candidates}), 200
    
    except Exception as e:
        print(f"Error processing candidate search: {e}")
        return jsonify({'error': str(e)}), 500
