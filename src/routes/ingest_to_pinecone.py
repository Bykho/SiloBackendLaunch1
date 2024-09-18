from flask import Flask
from flask_pymongo import PyMongo
from bson import ObjectId
from pinecone_utils import initialize_pinecone, get_embedding, upsert_vector
import os
from dotenv import load_dotenv

print("ingesting...")
load_dotenv()

app = Flask(__name__)
app.config["MONGO_URI"] = os.getenv("MONGO_URI")
mongo = PyMongo(app)

pinecone_index = initialize_pinecone()

def ingest_projects():
    projects = mongo.db.projects.find()
    for project in projects:
        project_content = f"{project['projectName']} {project['projectDescription']} {' '.join(project.get('tags', []))}"
        project_embedding = get_embedding(project_content)
        upsert_vector(pinecone_index, str(project['_id']), project_embedding, metadata={"type": "project", "project_id": str(project['_id'])})
        print(f"Ingested project: {project['projectName']}")

def ingest_users():
    users = mongo.db.users.find()
    for user in users:
        user_profile = f"{user.get('biography', '')} {' '.join(user.get('skills', []))} {' '.join(user.get('interests', []))}"
        user_embedding = get_embedding(user_profile)
        upsert_vector(pinecone_index, str(user['_id']), user_embedding, metadata={"type": "user", "username": user['username']})
        print(f"Ingested user: {user['username']}")

if __name__ == "__main__":
    print("Starting project ingestion...")
    ingest_projects()
    print("Project ingestion complete.")
    
    print("Starting user ingestion...")
    ingest_users()
    print("User ingestion complete.")