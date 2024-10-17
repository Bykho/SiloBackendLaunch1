

from flask import Blueprint, request, jsonify
import json
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from bson import ObjectId
from .. import mongo
from ..routes_schema_utility import get_user_details, get_user_context_details, get_user_feed_details, get_portfolio_details, get_project_feed_details, convert_objectid_to_str
import datetime
from ..routes.mixpanel_utils import track_event
from .pinecone_utils import *
from pymongo import MongoClient

MONGO_Research_URI = os.environ.get('MONGO_URI')
research_client = MongoClient(MONGO_Research_URI)
research_db = research_client['arxiv_database']
research_collection = research_db['arxiv_collection']


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
        print('project list: ', project_list)
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
    
@project_bp.route('/getSimilarProjectsBatch', methods=['POST'])
@jwt_required()
def get_similar_projects_batch():
    data = request.get_json()
    project_ids = data.get('projectIds')
    
    if not project_ids:
        return jsonify({"error": "Project IDs are required"}), 400
    
    similar_projects_map = {}
    for project_id in project_ids:
        # Fetch the embedding for the project
        result = pinecone_index.fetch([project_id])
        if project_id in result['vectors']:
            embedding = result['vectors'][project_id]['values']
            # Query similar projects
            similar_projects = query_similar_vectors_projects(pinecone_index, embedding, top_k=2)
            # Exclude the original project and format the results
            similar_project_ids = [
                match['id'] for match in similar_projects if match['id'] != project_id
            ]
            similar_projects_map[project_id] = similar_project_ids
        else:
            similar_projects_map[project_id] = []
    
    return jsonify(similar_projects_map), 200


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

@project_bp.route('/getSimilarResearchPapersBatch', methods=['POST'])
@jwt_required()
def get_similar_research_papers_batch():
    data = request.get_json()
    project_ids = data.get('projectIds')
    
    if not project_ids:
        return jsonify({"error": "Project IDs are required"}), 400
    
    similar_papers_map = {}
    for project_id in project_ids:
        # Fetch the embedding for the project
        result = pinecone_index.fetch(ids=[project_id])
        if 'vectors' in result and project_id in result['vectors']:
            embedding = result['vectors'][project_id]['values']
            # Query similar research papers
            similar_papers = query_similar_vectors_research(pinecone_index, embedding, top_k=3)
            # Extract mongo_id from metadata
            similar_paper_ids = [
                match['metadata']['mongo_id']
                for match in similar_papers
                if 'metadata' in match and 'mongo_id' in match['metadata']
            ]
            similar_papers_map[project_id] = similar_paper_ids
        else:
            similar_papers_map[project_id] = []
    
    return jsonify(similar_papers_map), 200

@project_bp.route('/returnResearchPapersFromIds', methods=['POST'])
@jwt_required()
def return_research_papers_from_ids():
    data = request.get_json()
    research_paper_ids = data.get('researchPaperIds')
    
    if not research_paper_ids:
        return jsonify({"error": "Research Paper IDs are required"}), 400
    
    try:
        # Convert string research paper IDs to ObjectId instances
        object_ids = [ObjectId(paper_id) for paper_id in research_paper_ids]
        
        # Fetch research papers from the research database using ObjectId
        research_papers = list(research_collection.find({'_id': {'$in': object_ids}}))
        
        # Convert ObjectId to string for the response
        for paper in research_papers:
            paper['_id'] = str(paper['_id'])
        
        return jsonify(research_papers), 200
    except Exception as e:
        return jsonify({"error": "Internal Server Error"}), 500
    
@project_bp.route('/getSimilarUsers', methods=['POST'])
@jwt_required()
def get_similar_users():
    data = request.get_json()
    user_id = data.get('user_id')   
    similar_users_map = {}

    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    
    similar_users = query_similar_vectors_users(pinecone_index, str(user_id), top_k=3)
    similar_user_ids = [ match['id'] for match in similar_users if match['id'] != user_id]
    similar_users_map[user_id] = similar_user_ids
    print("ids: ", similar_user_ids)
    return jsonify(similar_user_ids), 200



