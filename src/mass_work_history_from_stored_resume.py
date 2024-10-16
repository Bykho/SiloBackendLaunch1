import base64
import io
import logging
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
import os
from routes.resume_autofill_groq import extract_text_from_file, validate_and_regenerate_json
from werkzeug.datastructures import FileStorage

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

# Connect to MongoDB
client = MongoClient(os.getenv('MONGO_URI'))
db = client.get_database('DevelopmentDatabase')

def process_user_resumes():
    users = db.users.find({})
    total_users = 0
    processed_users = 0
    skipped_users = 0
    
    for user in users:
        total_users += 1
        if 'resume' in user and not user.get('workhistory'):
            resume_data = user['resume']
            
            try:
                # Check if resume_data is in the correct format
                if not resume_data.startswith('data:application/pdf;base64,'):
                    logging.warning(f"Invalid resume data format for user {user['_id']}")
                    skipped_users += 1
                    continue

                # Extract the base64 encoded content
                _, encoded_content = resume_data.split('base64,', 1)

                # Decode the content
                try:
                    file_content = base64.b64decode(encoded_content)
                except base64.binascii.Error:
                    logging.error(f"Invalid base64 encoding for user {user['_id']}")
                    skipped_users += 1
                    continue
                
                # Create a FileStorage object
                file = FileStorage(
                    stream=io.BytesIO(file_content),
                    filename='resume.pdf',
                    content_type='application/pdf'
                )
                
                # Extract text from the resume
                file_text = extract_text_from_file(file)
                
                # Process the text and get the summary
                summary = validate_and_regenerate_json(file_text)
                
                # Extract work history from the summary
                work_history = summary.get('workhistory', [])
                
                # Update the user's work history in the database
                db.users.update_one(
                    {'_id': user['_id']},
                    {'$set': {'workhistory': work_history}}
                )
                
                processed_users += 1
                logging.info(f"Updated work history for user: {user['_id']}")
            
            except Exception as e:
                logging.error(f"Error processing resume for user {user['_id']}: {str(e)}")
                skipped_users += 1
        else:
            skipped_users += 1

    logging.info(f"Total users: {total_users}")
    logging.info(f"Processed users: {processed_users}")
    logging.info(f"Skipped users: {skipped_users}")

if __name__ == '__main__':
    process_user_resumes()