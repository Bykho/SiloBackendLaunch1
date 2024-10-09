from flask import Flask
from flask_pymongo import PyMongo
from bson import ObjectId
from pinecone_utils import initialize_pinecone, get_embedding, upsert_vector
import os
from dotenv import load_dotenv
import PyPDF2
import uuid
import sys



print("ingesting...")
load_dotenv()

app = Flask(__name__)
app.config["MONGO_URI"] = os.getenv("MONGO_URI")
mongo = PyMongo(app)

pinecone_index = initialize_pinecone()

def ingest_projects():
    projects = mongo.db.projects.find()
    for project in projects:
        try:
            project_name = project['projectName']
            project_description = project['projectDescription']
            layers_text = []
            for layer in project.get('layers', []):
                layer_content = ' '.join([item['value'] for item in layer if isinstance(item['value'], str)])  # Extract text from layer
                layers_text.append(layer_content)

            layers_text_limited = layers_text[:5]  
            tags_limited = project.get('tags', [])[:10]  
            project_content = f"{project_name} {project_description} {' '.join(tags_limited)} {' '.join(layers_text_limited)}"
            if len(project_content) > 8000:
                project_content = project_content[:8000]  # Truncate to avoid exceeding token limits
            
            project_embedding = get_embedding(project_content)
            
            upsert_vector(pinecone_index, str(project['_id']), project_embedding, metadata={"type": "project", "project_id": str(project['_id'])})
            print(f"Ingested project: {project['projectName']}")
        except Exception as e:
            print(f"Error ingesting project: {project.get('projectName', 'Unknown')} - {e}")
            continue  # Skip this project and move to the next one


def ingest_users():
    users = mongo.db.users.find()
    for user in users:
        try:
            user_profile = f"{user.get('biography', '')} {' '.join(user.get('skills', []))} {' '.join(user.get('interests', []))}"
            portfolio_content = ""
            if 'portfolio' in user:
                for project_id in user['portfolio'][:3]: 
                    project = mongo.db.projects.find_one({"_id": ObjectId(project_id)})
                    
                    if project is None:
                        raise ValueError(f"Project with ID {project_id} not found for user {user['username']}")
                    project_name = project.get('projectName', '')
                    project_description = project.get('projectDescription', '')
                    
                    layers_text = []
                    for layer in project.get('layers', []):
                        layer_content = ' '.join([item['value'] for item in layer if isinstance(item['value'], str)])  # Extract text from layer
                        layers_text.append(layer_content)
                    
                    layers_text_limited = layers_text[:5]  # Limit the number of layers
                    project_content = f"{project_name} {project_description} {' '.join(layers_text_limited)}"
                    portfolio_content += f" {project_content}"
            
            full_user_profile = f"{user_profile} {portfolio_content[:8000]}"  # Truncate if too large
            user_embedding = get_embedding(full_user_profile)
            upsert_vector(pinecone_index, str(user['_id']), user_embedding, metadata={"type": "user", "username": user['username']})
            print(f"Ingested user: {user['username']}")
        except Exception as e:
            print(f"Error ingesting user: {user.get('username', 'Unknown')} - {e}")
            continue  # Skip this user and move to the next one


def ingest_pdf(pdf_path):
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text()

        if len(text) > 8000:
            text = text[:8000]

        pdf_embedding = get_embedding(text)

        pdf_id = str(uuid.uuid4())

        upsert_vector(pinecone_index, pdf_id, pdf_embedding, metadata={"type": "pdf", "filename": os.path.basename(pdf_path)})

        print(f"Ingested PDF: {os.path.basename(pdf_path)}")
        print(f"Vector ID: {pdf_id}")

        return pdf_id
    except Exception as e:
        print(f"Error ingesting PDF: {pdf_path} - {e}")
        return None


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # If a command-line argument is provided, treat it as the PDF path
        pdf_path = sys.argv[1]
        print(f"Ingesting PDF: {pdf_path}")
        pdf_id = ingest_pdf(pdf_path)
        if pdf_id:
            print(f"PDF ingested successfully. Vector ID: {pdf_id}")
        else:
            print("Failed to ingest PDF.")
    else:
        # If no command-line argument, proceed with project and user ingestion
        print("Starting project ingestion...")
        ingest_projects()
        print("Project ingestion complete.")
        
        print("Starting user ingestion...")
        ingest_users()
        print("User ingestion complete.")