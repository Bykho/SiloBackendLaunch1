# candidate_search_pinecone_testing.py

import os
import base64
import io
import re
from dotenv import load_dotenv
from pymongo import MongoClient
import pinecone
import openai
from PyPDF4 import PdfFileReader
from pdfminer.high_level import extract_text as pdfminer_extract
from PIL import Image
from pdf2image import convert_from_bytes
import pytesseract
from bson import ObjectId
from pinecone import Pinecone, ServerlessSpec



# Load environment variables from .env file
load_dotenv()

# Explicitly define other necessary keys
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
PINECONE_KEY = os.getenv('PINECONE_KEY')
PINECONE_ENVIRONMENT = 'us-east-1'
MONGO_URI = os.getenv('MONGO_URI')

# Initialize OpenAI
openai.api_key = OPENAI_API_KEY

# Initialize Pinecone instance
pc = Pinecone(
    api_key=PINECONE_KEY
)

INDEX_NAME = 'candidate-search-testing-productiondb'
# Connect to the Pinecone index
index = pc.Index(INDEX_NAME)

# Initialize MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client['ProductionDatabase']  # Replace with your actual database name
users_collection = db['users']
projects_collection = db['projects']

# Helper Functions

def extract_text_from_pdf(pdf_bytes):
    """
    Extract text from a PDF file using multiple methods.
    """
    text = ""

    # Method 1: PyPDF4 (for PDFs with embedded text)
    try:
        pdf_stream = io.BytesIO(pdf_bytes)
        reader = PdfFileReader(pdf_stream)
        for page_num in range(reader.numPages):
            page = reader.getPage(page_num)
            text += page.extractText() or ""
        if text.strip() and is_text_valid(text):
            return text.strip()
    except Exception as e:
        print(f"PyPDF4 extraction failed: {e}")

    # Method 2: pdfminer (for more complex PDFs with embedded text)
    try:
        pdf_stream = io.BytesIO(pdf_bytes)
        text = pdfminer_extract(pdf_stream)
        if text.strip() and is_text_valid(text):
            return text.strip()
    except Exception as e:
        print(f"pdfminer extraction failed: {e}")

    # Method 3: OCR with Tesseract (for scanned PDFs or images)
    if not is_text_valid(text):
        try:
            images = convert_from_bytes(pdf_bytes)
            for image in images:
                text += pytesseract.image_to_string(image)
            if text.strip():
                return text.strip()
        except Exception as e:
            print(f"OCR extraction failed: {e}")

    raise ValueError("Text extraction failed for all PDF methods.")

def is_text_valid(extracted_text):
    """
    Validate extracted text to ensure it's not garbled and has reasonable word length.
    """
    return (
        not is_text_garbled(extracted_text) and
        has_reasonable_word_length(extracted_text)
    )

def is_text_garbled(extracted_text):
    """
    Check if the text is garbled based on the ratio of non-alphanumeric characters.
    """
    non_alnum_count = sum(1 for char in extracted_text if not char.isalnum())
    total_char_count = len(extracted_text)

    if total_char_count == 0:
        return True  # Empty text is considered garbled

    non_alnum_ratio = non_alnum_count / total_char_count

    # If more than 40% of the text is non-alphanumeric, consider it garbled
    return non_alnum_ratio > 0.4

def has_reasonable_word_length(extracted_text, min_average_length=3):
    """
    Ensure the average word length is above a minimum threshold.
    """
    words = extracted_text.split()
    if not words:
        return False  # No words, likely garbled

    average_word_length = sum(len(word) for word in words) / len(words)

    # If the average word length is below 3 characters, consider it garbled
    return average_word_length >= min_average_length

def generate_embedding(text):
    """
    Generate embedding for the given text using OpenAI's Ada model.
    """
    try:
        response = openai.Embedding.create(
            input=text,
            model="text-embedding-ada-002"  # Ensure this model is available
        )
        embedding = response['data'][0]['embedding']
        return embedding
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return None



def process_resume(resume_base64):
    """
    Decode and extract text from a base64-encoded PDF resume.
    """
    try:
        # Remove the prefix if present
        if ',' in resume_base64:
            resume_base64 = resume_base64.split(',', 1)[1]
        resume_bytes = base64.b64decode(resume_base64)
        resume_text = extract_text_from_pdf(resume_bytes)
        return resume_text
    except Exception as e:
        print(f"Error processing resume: {e}")
        return ""

def extract_project_text(project):
    """
    Extract text from a project, excluding images but including PDFs.
    """
    text = ""
    layers = project.get('layers', [])
    
    for layer in layers:
        if isinstance(layer, list):
            for item in layer:
                if isinstance(item, dict):
                    item_type = item.get('type')
                    
                    if item_type == 'text':
                        # Append text content
                        text += item.get('value', '') + " "
                    
                    elif item_type == 'pdf':
                        # Extract and append text from embedded PDF
                        pdf_base64 = item.get('value', '')
                        if pdf_base64:
                            try:
                                # Remove data URI scheme if present
                                if ',' in pdf_base64:
                                    pdf_base64 = pdf_base64.split(',', 1)[1]
                                
                                # Decode base64 to bytes
                                pdf_bytes = base64.b64decode(pdf_base64)
                                
                                # Extract text from PDF
                                pdf_text = extract_text_from_pdf(pdf_bytes)
                                
                                text += pdf_text + " "
                            except Exception as e:
                                print(f"Error extracting text from PDF in project {project.get('projectName', 'N/A')}: {e}")
    
    return text.strip()


def extract_work_history_text(workhistory):
    """
    Extract text from the user's work history, skipping if workhistory is not a dictionary.
    """
    if not isinstance(workhistory, dict):
        return ""  # Return an empty string if workhistory is not a dictionary

    text = ""
    for experience_key, experience in workhistory.items():
        if isinstance(experience, dict):
            role = experience.get('role', '')
            description = experience.get('description', '')
            text += f"{role}: {description} "
    return text.strip()

def extract_full_profile(user):
    """
    Compile the full profile text for a user.
    """
    profile_fields = [
        user.get('username', ''),
        user.get('email', ''),
        user.get('university', ''),
        user.get('major', ''),
        user.get('biography', ''),
        ', '.join(user.get('skills', [])),
        ', '.join(user.get('interests', [])),
    ]
    full_profile = ' '.join(filter(None, profile_fields))
    return full_profile.strip()

def upsert_embedding(vector, metadata):
    """
    Upsert a single embedding into Pinecone, ensuring metadata values are valid types.
    """
    # Convert any None values in metadata to empty strings
    sanitized_metadata = {k: (v if v is not None else "") for k, v in metadata.items()}
    
    try:
        index.upsert(
            vectors=[(sanitized_metadata['id'], vector, sanitized_metadata)]
        )
    except Exception as e:
        print(f"Error upserting to Pinecone: {e}")

def main():
    users = users_collection.find()
    total_users = users_collection.count_documents({})
    print(f"Total users to process: {total_users}")

    for user in users:
        user_id = str(user['_id'])
        username = user.get('username', 'N/A')

        # 1. Embed Full User Profile
        full_profile_text = extract_full_profile(user)
        if full_profile_text:
            full_embedding = generate_embedding(full_profile_text)
            if full_embedding:
                metadata = {
                    'id': f"{user_id}_full_user",  # Add this line
                    'user_id': user_id,
                    'username': username,
                    'project_id': None,
                    'type': 'full user'
                }
                upsert_embedding(full_embedding, metadata)
                print(f"Upserted full profile for user: {username}")
        
        # 2. Embed Resume
        resume_base64 = user.get('resume', '')
        if resume_base64:
            resume_text = process_resume(resume_base64)
            if resume_text:
                resume_embedding = generate_embedding(resume_text)
                if resume_embedding:
                    metadata = {
                        'id': f"{user_id}_resume",  # Add this line
                        'user_id': user_id,
                        'username': username,
                        'project_id': None,
                        'type': 'resume'
                    }
                    upsert_embedding(resume_embedding, metadata)
                    print(f"Upserted resume for user: {username}")
        
        # 3. Embed Each Project in Portfolio
        portfolio_ids = user.get('portfolio', [])
        for project_id in portfolio_ids:
            project = projects_collection.find_one({'_id': ObjectId(project_id)})
            if project:
                project_text = extract_project_text(project)
                if project_text:
                    project_embedding = generate_embedding(project_text)
                    if project_embedding:
                        metadata = {
                            'id': f"{user_id}_project_{project_id}",  # Add this line
                            'user_id': user_id,
                            'username': username,
                            'project_id': str(project['_id']),
                            'type': 'portfolio entry'
                        }
                        upsert_embedding(project_embedding, metadata)
                        print(f"Upserted portfolio project: {project.get('projectName', 'N/A')} for user: {username}")
        
        # 4. Embed Each Work Experience
        workhistory = user.get('workhistory', {})
        work_experiences = extract_work_history_text(workhistory)
        if work_experiences:  # Only upsert if work_experiences is not empty
            work_embedding = generate_embedding(work_experiences)
            if work_embedding:
                metadata = {
                    'id': f"{user_id}_work_experience",  # Unique ID for Pinecone
                    'user_id': user_id,
                    'username': username,
                    'project_id': None,
                    'type': 'work experience'
                }
                upsert_embedding(work_embedding, metadata)
                print(f"Upserted work experience for user: {username}")

    print("Embedding process completed.")



if __name__ == "__main__":
    main()
