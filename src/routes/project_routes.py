

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from bson import ObjectId
from .. import mongo
from ..routes_schema_utility import get_user_details, get_user_context_details, get_user_feed_details, get_portfolio_details, get_project_feed_details, convert_objectid_to_str
import datetime
from ..routes.mixpanel_utils import track_event
from .pinecone_utils import *
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename
import os
import io
import PyPDF4
from pdfminer.high_level import extract_text as pdfminer_extract
import pytesseract
from pdf2image import convert_from_bytes

project_bp = Blueprint('project', __name__)
pinecone_index = initialize_pinecone()


@project_bp.route('/returnProjectsFromIds', methods=['POST'])
@jwt_required()
def return_projects_from_ids():
    print()
    print('go into return projects from ids')
    data = request.get_json()
    print('here is the data sent from frontend in returnProjectsFromIDS: ', data)
    project_ids = data.get('projectIds')
    if project_ids is None:  # Check if 'projectIds' key is present
        return jsonify({"error": "Project IDs are required"}), 400
    if not project_ids:  # If 'projectIds' is an empty list
        return jsonify([]), 200  # Return an empty list of projects
    try:
        project_ids = [ObjectId(project_id) for project_id in project_ids]
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    try:
        projects = mongo.db.projects.find({"_id": {"$in": project_ids}})
        project_list = []
        for project in projects:
            project = convert_objectid_to_str(project)
            project_list.append({
                "_id": str(project["_id"]),
                "projectName": project.get("projectName", ""),
                "projectDescription": project.get("projectDescription", ""),
                "createdBy": str(project.get("createdBy", "")),
                "upvotes": [str(upvote_id) for upvote_id in project.get("upvotes", [])],
                "tags": project.get("tags", []),
                "layers": project.get("layers", []),
                "links": project.get("links", []),
                "created_at": project.get("created_at", ""),
                "comments": project.get("comments", []),
                "visibility": project.get("visibility", True)
            })
        #print('proejcts from ids project list: ', project_list)
        project_list = convert_objectid_to_str(project_list)
        return jsonify(project_list), 200
    except Exception as e:
        print(f"Error fetching projects: {e}")
        return jsonify({"error": "Failed to fetch projects"}), 500



@project_bp.route('/addBlocProject', methods=['POST'])
@jwt_required()
def add_bloc_project():
    print('opened the route')
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')
    print('User ID from JWT:', user_id)
    data = request.get_json()
    project_data = data.get('data')
    print('got the project keys, ', project_data.keys())
    if not project_data:
        return jsonify({"error": "No project data provided"}), 400
    project_id = project_data.get('_id')
    if project_id:
        update_result = mongo.db.projects.update_one(
            {"_id": ObjectId(project_id)},
            {"$set": {
                "projectName": project_data.get('projectName'),
                "links": project_data.get('links'),
                "projectDescription": project_data.get('projectDescription'),
                "layers": project_data.get('layers'),
                "updated_at": datetime.datetime.utcnow(),
                "tags": project_data.get('tags'),
                "visibility": project_data.get('visibility', True)
            }}
        )
        if update_result.modified_count == 1:
            updated_project = mongo.db.projects.find_one({"_id": ObjectId(project_id)})
            updated_project = convert_objectid_to_str(updated_project)
            print('here is the project getting sent up, ', updated_project)
            track_event(str(user_id), "project edited", {"project_id": str(project_id), "action": "update"})

            return jsonify(updated_project), 200
        else:
            return jsonify({"error": "Failed to update project"}), 500
    else:
        print('got passed the else stage')
        user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
        print('User found for update:', user)
        new_project = {
            "comments": [],
            "createdBy": user.get('username'),
            "projectName": project_data.get('projectName'),
            "links": project_data.get('links'),
            'upvotes': [],
            'user_id': user_id, 
            'tags': project_data.get('tags'),
            "projectDescription": project_data.get('projectDescription'),
            "layers": project_data.get('layers'),
            "created_at": datetime.datetime.utcnow(),
            "visibility": project_data.get('visibility', True)
        }
        result = mongo.db.projects.insert_one(new_project)
        print('here is the result: ', result)
        print('here is the project getting sent up, ', new_project)
        if result.acknowledged:
            print('got passed the result.acknowleged')
            project_id = str(result.inserted_id)
            new_project["_id"] = project_id
            new_project = convert_objectid_to_str(new_project)

            print(f"\n \n Here is the new project \n \n {new_project} \n \n \n")

            layer_texts = []
            for layer in project_data.get('layers', []):
                for item in layer:
                    if item.get('type') == "text":  # Check if the type is 'text'
                        layer_texts.append(item.get('value', ''))  # Append the value if it's of type 'text'


            # On new project creation, add a new embedding to Pinecone 
            project_content = f"{new_project['projectName']} {new_project['projectDescription']} {' '.join(new_project.get('tags', []))} {' '.join(layer_texts)}"
            project_embedding = get_embedding(project_content)
            upsert_vector(pinecone_index, str(new_project['_id']), project_embedding, metadata={"type": "project", "project_id": str(new_project['_id'])}) 

            # Log the user document to debug the update issue
            if not user:
                print('User not found in the database')
                return jsonify({"error": "User not found"}), 404
            # Add the project ID to the user's portfolio
            update_result = mongo.db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$push": {"portfolio": {"$each": [project_id], "$position": 0}}}
            )
            print('update_result: ', update_result)
            if update_result.modified_count == 1:
                track_event(str(user_id), "project added", {"project_id": str(project_id), "action": "create"})
                """ Adding new project to Pinecone 
                project_content = f"{project['projectName']} {project['projectDescription']} {' '.join(project.get('tags', []))}"
                project_embedding = get_embedding(project_content)
                upsert_vector(pinecone_index, str(project['_id']), project_embedding, metadata={"project_id": str(project['_id'])})
                """
                return jsonify(new_project), 201
            else:
                print('couldnt process the update')
                return jsonify({"error": "Failed to update user's portfolio"}), 500
        else:
            print('the result was not acknowledged')
            return jsonify({"error": "Failed to add project"}), 500

@project_bp.route('/returnUserProjects', methods=['POST'])
@jwt_required()
def return_user_projects():
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')    
    data = request.get_json()

    if not user_id:
        return jsonify({"error": "User ID is required"}), 400

    try:
        user_id = ObjectId(user_id)
        print('got passed that^')
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    user = mongo.db.users.find_one({"_id": user_id})
    if not user:
        return jsonify({"error": "User not found"}), 404
    try:
        project_ids = [ObjectId(pid) for pid in user.get('portfolio', [])]
        projects = mongo.db.projects.find({"_id": {"$in": project_ids}})
        project_list = []
        for project in projects:
            project_list.append({
                "_id": str(project["_id"]),
                "projectName": project["projectName"]
            })
        return jsonify(project_list), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@project_bp.route('/candidateSearch', methods=['POST'])
@jwt_required()
def candidateSearch():
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

        # Get embedding for the extracted text
        job_embedding = get_embedding(text)

        # Query similar vectors without inserting the job vector
        similar_vectors = query_similar_vectors(pinecone_index, job_embedding, top_k=10)

        # Process results
        results = []
        for match in similar_vectors:
            results.append({
                "id": match['id'],
                "score": match['score'],
                "metadata": match['metadata']
            })

        return jsonify({'results': results}), 200
    
    except Exception as e:
        print(f"Error processing file: {e}")
        return jsonify({'error': str(e)}), 500

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




@project_bp.route('/getSimilarProjectsBatch', methods=['POST'])
@jwt_required()
def get_similar_projects_batch():
    print('opened getSimilarProjectsBatch route')
    
    try:
        data = request.get_json()
        print(f'Received data: {data}')  # Log the received data
        
        # Get projectIds, default to an empty list if missing
        project_ids = data.get('projectIds', [])
        
        similar_projects_map = {}
        print(f'Starting to process project IDs: {project_ids}')  # Log the project IDs
        
        # If project_ids is empty, skip processing and return the empty map
        if len(project_ids) == 0:
            print('No project IDs provided, returning empty similar_projects_map')
            return jsonify(similar_projects_map), 200
        
        for project_id in project_ids:
            print(f'Processing project ID: {project_id}')  # Log each project being processed
            
            # Fetch the embedding for the project
            result = pinecone_index.fetch([project_id])
            print(f'Pinecone fetch result for {project_id}: {result}')  # Log Pinecone fetch result
            
            if project_id in result.get('vectors', {}):
                embedding = result['vectors'][project_id]['values']
                print(f'Embedding for {project_id}: {embedding}')  # Log the embedding

                # Query similar projects
                similar_projects = query_similar_vectors_projects(pinecone_index, embedding, top_k=5)
                print(f'Similar projects for {project_id}: {similar_projects}')  # Log similar projects

                # Exclude the original project and format the results
                similar_project_ids = [
                    match['id'] for match in similar_projects if match['id'] != project_id
                ]
                print(f'Filtered similar project IDs for {project_id}: {similar_project_ids}')  # Log filtered project IDs
                
                similar_projects_map[project_id] = similar_project_ids
            else:
                print(f'No vectors found for project ID: {project_id}')  # Log if no vector is found
                similar_projects_map[project_id] = []
        
        print(f'Final similar projects map: {similar_projects_map}')  # Log the final result
        
        return jsonify(similar_projects_map), 200

    except Exception as e:
        print(f'Error occurred: {e}')  # Log any exceptions
        return jsonify({"error": "An error occurred while processing the request"}), 500


@project_bp.route('/deleteProject', methods=['DELETE'])
@jwt_required()
def delete_project():
    print('deleting project')
    data = request.get_json()
    project_id = data.get('projectId')
    user_id = data.get('userId')
    print(f"projectID: {project_id}, userID: {user_id}, data: {data}")
    
    if not project_id or not user_id:
        return jsonify({"error": "Project ID and User ID are required"}), 400

    try:
        project_object_id = ObjectId(project_id)
        user_object_id = ObjectId(user_id)
    except Exception as e:
        return jsonify({"error": f"Invalid ObjectId: {str(e)}"}), 400

    try:
        # Delete the project from the projects collection
        project_delete_result = mongo.db.projects.delete_one({"_id": project_object_id})
        if project_delete_result.deleted_count != 1:
            return jsonify({"error": "Failed to delete the project from the projects collection"}), 500
        print('Project deleted from projects collection')

        # Remove the project ID from the user's portfolio
        user_update_result = mongo.db.users.update_one(
            {"_id": user_object_id},
            {"$pull": {"portfolio": str(project_id)}}
        )
        if user_update_result.modified_count != 1:
            print(f"User update result: {user_update_result.raw_result}")
            return jsonify({"error": "Failed to update the user's portfolio"}), 500
        print('Project ID removed from user portfolio')
        
        # Delete from Pinecone index
        try:
            pinecone_index.delete(ids=[str(project_id)])
        except Exception as e:
            print(f"Error deleting from Pinecone: {str(e)}")
            # Don't return here, as the main operation was successful

        return jsonify({"message": "Project deleted successfully"}), 200
    except Exception as e:
        print(f"Error in delete_project: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@project_bp.route('/updateProject', methods=['POST'])
@jwt_required()
def update_project(project_name):
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')
    print('User ID from JWT:', user_id)
    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        return jsonify({"error": "User not found"}), 404
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid data"}), 422
    project_index = next((index for (index, project) in enumerate(user['portfolio']) if project['projectName'] == project_name), None)
    if project_index is None:
        return jsonify({"error": "Project not found"}), 404
    for key in data:
        user['portfolio'][project_index][key] = data[key]
    mongo.db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"portfolio": user['portfolio']}})
    # Update the Pinecone vector
    project_content = f"{user['portfolio'][project_index]['projectName']} {user['portfolio'][project_index]['projectDescription']} {' '.join(user['portfolio'][project_index].get('tags', []))}"
    project_embedding = get_embedding(project_content)
    upsert_vector(pinecone_index, str(user['portfolio'][project_index]['_id']), project_embedding, metadata={"type": "project", "project_id": str(user['portfolio'][project_index]['_id'])})
    return jsonify({'message': 'Project updated successfully'}), 200


