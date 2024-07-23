

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId
from .. import mongo
from ..routes_schema_utility import get_user_details, get_user_context_details, get_user_feed_details, get_portfolio_details, get_project_feed_details, convert_objectid_to_str
import datetime

project_bp = Blueprint('project', __name__)

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
    username = get_jwt_identity()
    print('Username from JWT:', username)
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
                "updated_at": datetime.datetime.utcnow()
            }}
        )
        if update_result.modified_count == 1:
            updated_project = mongo.db.projects.find_one({"_id": ObjectId(project_id)})
            updated_project = convert_objectid_to_str(updated_project)  # Use your function
            print('here is the project getting sent up, ', updated_project)

            return jsonify(updated_project), 200
        else:
            return jsonify({"error": "Failed to update project"}), 500
    else:
        print('got passed the else stage')
        new_project = {
            "comments": [],
            "createdBy": username,
            "projectName": project_data.get('projectName'),
            "links": project_data.get('links'),
            'upvotes': [],
            "projectDescription": project_data.get('projectDescription'),
            "layers": project_data.get('layers'),
            "created_at": datetime.datetime.utcnow()
        }
        result = mongo.db.projects.insert_one(new_project)
        print('here is the result: ', result)
        print('here is the project getting sent up, ', new_project)
        if result.acknowledged:
            print('got passed the result.acknowleged')
            project_id = str(result.inserted_id)
            new_project["_id"] = project_id
            new_project = convert_objectid_to_str(new_project) 
            # Log the user document to debug the update issue
            user = mongo.db.users.find_one({"username": username})
            print('User found for update:', user)
            if not user:
                print('User not found in the database')
                return jsonify({"error": "User not found"}), 404
            # Add the project ID to the user's portfolio
            update_result = mongo.db.users.update_one(
                {"username": username},
                {"$push": {"portfolio": project_id}}
            )
            print('update_result: ', update_result)
            if update_result.modified_count == 1:
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
    data = request.get_json()
    user_id = data.get('userId')

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

@project_bp.route('/deleteProject', methods=['DELETE'])
@jwt_required()
def delete_project():
    data = request.get_json()
    project_id = data.get('projectId')
    user_id = data.get('userId')

    if not project_id or not user_id:
        return jsonify({"error": "Project ID and User ID are required"}), 400

    try:
        project_object_id = ObjectId(project_id)
        user_object_id = ObjectId(user_id)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    # Delete the project from the projects collection
    project_delete_result = mongo.db.projects.delete_one({"_id": project_object_id})
    if project_delete_result.deleted_count != 1:
        return jsonify({"error": "Failed to delete the project from the projects collection"}), 500

    # Remove the project ID from the user's portfolio
    user_update_result = mongo.db.users.update_one(
        {"_id": user_object_id},
        {"$pull": {"portfolio": project_id}}
    )
    if user_update_result.modified_count != 1:
        return jsonify({"error": "Failed to update the user's portfolio"}), 500

    return jsonify({"message": "Project deleted successfully"}), 200


@project_bp.route('/updateProject', methods=['POST'])
@jwt_required()
def update_project(project_name):
    username = get_jwt_identity()
    user = mongo.db.users.find_one({"username": username})
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
    mongo.db.users.update_one({"username": username}, {"$set": {"portfolio": user['portfolio']}})
    return jsonify({'message': 'Project updated successfully'}), 200


