


from flask import Blueprint, request, jsonify, send_from_directory
from flask import current_app as app
from flask_cors import cross_origin
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt
import os
import openai
from dotenv import load_dotenv
import datetime
import uuid
import hashlib
from bson import json_util, ObjectId
import copy
from .routes_schema_utility import get_user_details, get_user_context_details, get_user_feed_details, get_portfolio_details, get_project_feed_details
from .fake_data import sample_users
from . import mongo
import logging

load_dotenv()
openai.api_key = os.getenv('OPENAI_API_KEY')

main_bp = Blueprint('main', __name__)

def convert_objectid_to_str(data):
    if isinstance(data, list):
        return [convert_objectid_to_str(item) for item in data]
    elif isinstance(data, dict):
        return {key: convert_objectid_to_str(value) for key, value in data.items()}
    elif isinstance(data, ObjectId):
        return str(data)
    else:
        return data

@main_bp.route('/joinGroup', methods=['POST'])
@jwt_required()
def join_group():
    print()
    #print('entered the /joinGroup route')
    username = get_jwt_identity()
    #print('here is the username: ', username)
    user = mongo.db.users.find_one({"username": username})
    #print('here is the user: ',user)
    if not user:
        return jsonify({"error": "User not found"}), 404
    data = request.get_json()
    print('here is the data, ', data)
    group_id = data.get('groupId')
    if not group_id:
        return jsonify({"error": "Group ID is required"}), 400
    group = mongo.db.groups.find_one({"_id": ObjectId(group_id)})
    print('here is the group: ', group)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    if user['_id'] in group['users']:
        return jsonify({"error": "User already in the group"}), 400
    mongo.db.groups.update_one(
        {"_id": ObjectId(group_id)},
        {"$push": {"users": user['_id']}}
    )
    mongo.db.users.update_one(
        {"_id": user['_id']},
        {"$push": {"groups": ObjectId(group_id)}}
    )
    return jsonify({"message": "Successfully joined the group"}), 200


@main_bp.route('/getCommentsByIds', methods=['POST'])
@jwt_required()
def get_comments_by_ids():
    data = request.get_json()
    comment_ids = data.get('commentIds')
    if not comment_ids:
        return jsonify({"error": "Comment IDs are required"}), 400

    try:
        comment_ids = [ObjectId(comment_id) for comment_id in comment_ids]
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    try:
        comments = mongo.db.comments.find({"_id": {"$in": comment_ids}})
        comment_list = []
        for comment in comments:
            comment_list.append({
                "_id": str(comment["_id"]),
                "author": comment.get("author", ""),
                "text": comment.get("text", ""),
                "group_target": str(comment.get("group_target", "")),
                "upvotes": [str(upvote_id) for upvote_id in comment.get("upvotes", [])],
            })
        return jsonify(comment_list), 200
    except Exception as e:
        return jsonify({"error": f"Error fetching comments: {e}"}), 500



@main_bp.route('/handleGroupComment', methods=['POST'])
@jwt_required()
def handle_group_comment():
    try:
        data = request.get_json()
        comment_text = data.get('text')
        group_id = data.get('groupId')
        title = data.get('title')
        print('/HANDLEGROUPCOMMENT: comment_text, ', comment_text)
        print('/HANDLEGROUPCOMMENT: group_id, ', group_id)
        print('/HANDLEGROUPCOMMENT: title, ', title)

        if not comment_text or not group_id or not title:
            return jsonify({"error": "Text, group ID, and title are required"}), 400
        group = mongo.db.groups.find_one({"_id": ObjectId(group_id)})
        if not group:
            return jsonify({"error": "Group not found"}), 404
        user = mongo.db.users.find_one({"username": get_jwt_identity()})
        if not user:
            return jsonify({"error": "User not found"}), 404
        new_comment = {
            "_id": ObjectId(),
            "author_id": user['_id'],
            "author": user['username'],
            "text": comment_text,
            "group_target": ObjectId(group_id),
            "upvotes": []
        }
        # Insert new comment into comments collection
        mongo.db.comments.insert_one(new_comment)
        # Ensure the comment_json field is initialized as an array if it doesn't exist
        if title not in group['comment_json']:
            group['comment_json'][title] = []
        # Update group's comment_json field
        mongo.db.groups.update_one(
            {"_id": ObjectId(group_id)},
            {"$push": {f"comment_json.{title}": new_comment["_id"]}}
        )
        # Update user's comments field
        mongo.db.users.update_one(
            {"_id": user['_id']},
            {"$push": {"comments": new_comment["_id"]}}
        )
        # Fetch updated comments
        updated_group = mongo.db.groups.find_one({"_id": ObjectId(group_id)})
        updated_comments = [str(comment_id) for comment_id in updated_group['comment_json'][title]]
        return jsonify({"message": "Successfully added comment", "updatedComments": updated_comments}), 200
    except Exception as e:
        print(f"Error handling group comment: {e}")
        return jsonify({"error": "Failed to handle comment"}), 500




@main_bp.route('/getUsersByIds', methods=['POST'])
@jwt_required()
def get_users_by_ids():
    data = request.get_json()
    user_ids = data.get('userIds')
    print('/getUsersByIds here is the data: ', data)

    if not user_ids:
        return jsonify({"error": "User IDs are required"}), 400

    try:
        user_ids = [ObjectId(user_id) for user_id in user_ids]
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    try:
        users = mongo.db.users.find({"_id": {"$in": user_ids}})
        user_list = []
        for user in users:
            user_list.append({
                "_id": str(user["_id"]),
                "username": user.get("username", ""),
                "email": user.get("email", ""),
                "user_type": user.get("user_type", ""),
                "interests": user.get("interests", []),
                "orgs": user.get("orgs", []),
            })
        return jsonify(user_list), 200
    except Exception as e:
        print(f"Error fetching users: {e}")
        return jsonify({"error": "Failed to fetch users"}), 500



@main_bp.route('/returnProjectsFromIds', methods=['POST'])
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





@main_bp.route('/saveProjectToGroup', methods=['POST'])
@jwt_required()
def save_project_to_group():
    print()
    print('saving projects to group')
    data = request.get_json()
    print('here is the data: ', data)
    group_id = data.get('groupId')
    project_ids = data.get('projectIds', [])
    print('here is the group id in /saveProjectToGroup', str(group_id))
    if not group_id or not project_ids:
        return jsonify({"error": "Group ID and Project IDs are required"}), 400

    try:
        group_id = ObjectId(group_id)
        project_ids = [ObjectId(project_id) for project_id in project_ids]
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    group = mongo.db.groups.find_one({"_id": group_id})
    if not group:
        return jsonify({"error": "Group not found"}), 404

    mongo.db.groups.update_one(
        {"_id": group_id},
        {"$push": {"projects": {"$each": project_ids}}}
    )

    return jsonify({"message": "Successfully added projects to group"}), 200


@main_bp.route('/groupCreate', methods=['POST'])
@jwt_required()
def groupCreate():
    username = get_jwt_identity()
    user = mongo.db.users.find_one({"username": username})

    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()
    if not data or 'groupName' not in data or 'groupDescription' not in data:
        return jsonify({"error": "Invalid data"}), 422

    new_group = {
        'groupName': data['groupName'],
        'groupDescription': data['groupDescription'],
        'createdBy': username,
        'users': [],
        'project_content': data['groupProject_Content'],
        'projects': [],
        'comment_json': {'General Discussion': []},  # Initialize as an array
        'created_at': datetime.datetime.utcnow(),
    }

    group_insert_result = mongo.db.groups.insert_one(new_group)
    group_id = group_insert_result.inserted_id

    return jsonify({"message": "Group created successfully", "group_id": str(group_id)}), 200






@main_bp.route('/returnGroups', methods=['GET'])
@jwt_required()
def return_groups():
    try:
        groups = mongo.db.groups.find()
        group_list = []
        for group in groups:
            group_list.append({
                "_id": str(group["_id"]),  # Convert ObjectId to string
                "name": group["groupName"],
                "description": group["groupDescription"],
                "createdBy": group["createdBy"],
                "users": [str(user_id) for user_id in group["users"]],  # Convert each user_id to string
                "project_content": group["project_content"],
                "comment_json": group.get("comment_json", {}),  # Include comment_json or an empty JSON object
                "created_at": group["created_at"],
                "projects": [str(project_id) for project_id in group.get("projects", [])]  # Convert project ObjectId to string
            })
        group_list = convert_objectid_to_str(group_list)
        return jsonify(group_list), 200
    except Exception as e:
        print(f"Error fetching groups: {e}")
        return jsonify({"error": "Failed to fetch groups"}), 500


@main_bp.route('/returnMyGroups', methods=['GET'])
@jwt_required()
def returnMyGroups():
    username = get_jwt_identity()
    user = mongo.db.users.find_one({"username": username})
    if not user:
        return jsonify({"error": "User not found"}), 404

    group_ids = user.get('groups', [])
    try:
        # Convert group_ids to ObjectId if they are not already
        group_ids = [ObjectId(group_id) if not isinstance(group_id, ObjectId) else group_id for group_id in group_ids]
        group_list = mongo.db.groups.find({"_id": {"$in": group_ids}})
        groups_to_be_returned = []
        for group in group_list:
            groups_to_be_returned.append({
                "_id": str(group["_id"]),  # Convert ObjectId to string
                "name": group["groupName"],
                "description": group["groupDescription"],
                "createdBy": group["createdBy"],
                "users": [str(user_id) for user_id in group["users"]],  # Convert each user_id to string
                "project_content": group["project_content"],
                "comment_json": group.get("comment_json", {}),  # Include comment_json or an empty JSON object
                "created_at": group["created_at"],
                "projects": [str(project_id) for project_id in group.get("projects", [])]  # Convert project ObjectId to string
            })
        #print('RETURNMYGROUPS groups_to_be_returned: ', groups_to_be_returned)
        print('/RETURNMYGROUPS here is groups_to_be_returned: ', groups_to_be_returned)
        groups_to_be_returned = convert_objectid_to_str(groups_to_be_returned)
        return jsonify(groups_to_be_returned), 200
    except Exception as e:
        print(f"Error fetching groups: {e}")
        return jsonify({"error": "Failed to fetch groups"}), 500

@main_bp.route('/updateCommentJson', methods=['POST'])
@jwt_required()
def update_comment_json():
    data = request.get_json()
    group_id = data.get('groupId')
    comment_json = data.get('comment_json')

    if not group_id or comment_json is None:
        return jsonify({"error": "Group ID and comment_json are required"}), 400

    try:
        group_id = ObjectId(group_id)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    try:
        mongo.db.groups.update_one(
            {"_id": group_id},
            {"$set": {"comment_json": comment_json}}
        )
        return jsonify({"message": "Successfully updated comment_json"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500




@main_bp.route('/returnUserProjects', methods=['POST'])
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


# Function to summarize text using OpenAI
def summarize_text_for_sign(text):
    try:
        print('Got to summarize text')
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content."},
                {"role": "user", "content": f"For the following resume, please write a concise (less than 100 words) bio for this person in the first person, also provide lists for suggested interests, suggested skills, a string for their latest university, a string for major, and a string for graduation year. If there are projects on the resume, also include the title of the project and its description. Please always format your response as a json with keys: bio, skills, interests, latestUniversity, major, grad_yr, projects (with contents title and desc). This is very important: the entirety of your response should constitute a valid JSON. There should be no json tags in the front or any leading/trailing text. Only give the json.  Here is the text:\n\n{text}"}
            ],
            max_tokens=600,
            n=1,
            stop=None,
            temperature=0.5
        )
        print(f'Here is the response {response}')
        return response.choices[0].message['content'].strip()
    except Exception as e:
        print(f"Error summarizing text: {e}")
        return ""

# Route for resume parsing
@main_bp.route('/resumeParser', methods=['POST', 'OPTIONS'])
@cross_origin()
def resume_parser():
    print('Opened the resume parser route')
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'}), 200
    data = request.get_json()
    if not data or 'resumeText' not in data:
        return jsonify({'error': 'No resume text provided'}), 400
    file_text = data['resumeText']
    try:
        summary = summarize_text_for_sign(file_text)
        print(f'here is the summary: {summary}')
        return jsonify({'summary': summary}), 200
    except Exception as e:
        print(f"Error parsing resume: {e}")
        return jsonify({'error': 'Failed to parse resume'}), 500


@main_bp.route('/')
def hello():
    return 'This 1 Message Means that heroku is running correctly!'

@main_bp.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('src/static/images', path)

def generate_unique_key():
    random_uuid = uuid.uuid4().hex
    sha256_hash = hashlib.sha256(random_uuid.encode()).hexdigest()
    unique_key = sha256_hash[:16]
    return unique_key

def convert_objectid_to_str(data):
    if isinstance(data, list):
        return [convert_objectid_to_str(item) for item in data]
    elif isinstance(data, dict):
        return {key: convert_objectid_to_str(value) for key, value in data.items()}
    elif isinstance(data, ObjectId):
        return str(data)
    else:
        return data


# Route to create access key

@main_bp.route('/createAccessKey', methods=['POST'])
@jwt_required()
def create_access_key():
    print('createAccessKey')
    data = request.get_json()
    created_by = data.get('created_by')
    print('data')
    new_key = generate_unique_key()  # Replace with actual key generation logic
    mongo.db.access_keys.insert_one({
        "key": new_key,
        "used": False,
        "created_by": created_by
    })
    print('Access key created:', new_key)
    return jsonify({"message": "Access key created", "key": new_key}), 201

@main_bp.route('/checkAccessKey', methods=['POST'])
def check_access_key():
    data = request.get_json()
    access_key = data.get('access_key')
    if not access_key:
        return jsonify({"message": "Access key is required"}), 400
    key_entry = mongo.db.access_keys.find_one({"key": access_key, "used": False})
    if key_entry:
        return jsonify({"message": "Access key is valid"}), 200
    else:
        return jsonify({"message": "Invalid or used access key"}), 404


# Route to join waiting list

@main_bp.route('/joinWaitingList', methods=['POST'])
def join_waiting_list():
    data = request.get_json()
    email = data.get('email')
    full_name = data.get('full_name')
    if not email or not full_name:
        return jsonify({"error": "Email and full name are required"}), 400
    if mongo.db.waiting_list.find_one({"email": email}):
        return jsonify({"error": "Email already in waiting list"}), 409
    mongo.db.waiting_list.insert_one({
        "email": email,
        "full_name": full_name,
        "timestamp": datetime.datetime.utcnow()
    })
    return jsonify({"message": "Email added to waiting list"}), 201


from bson import ObjectId

@main_bp.route('/SignUp', methods=['POST', 'OPTIONS'])
def register():
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization'
        }
        return ('', 204, headers)

    data = request.get_json()
    password = data.get('password')
    email = data.get('email')
    username = data.get('username')
    major = data.get('major')  # Get the user's major from the request data

    if not mongo.db.users.find_one({"email": email}):
        hashed_password = generate_password_hash(password)
        data['password'] = str(hashed_password)
        result = mongo.db.users.insert_one(data)
        user = mongo.db.users.find_one({"_id": result.inserted_id})
        user_details = get_user_context_details(user)
        user_details['_id'] = str(user['_id'])
        user['_id'] = str(user['_id'])
        access_token = create_access_token(identity=username, additional_claims=user_details)

        # Check if a group with the user's major exists
        group = mongo.db.groups.find_one({"groupName": major})
        if group:
            # Add user to the existing group
            mongo.db.groups.update_one(
                {"_id": ObjectId(group['_id'])},
                {"$push": {"users": ObjectId(user['_id'])}}
            )
            updated_group = mongo.db.groups.find_one({"_id": ObjectId(group['_id'])})
            print(f"User {user['_id']} added to group {group['_id']}. Updated group: {updated_group}")

            mongo.db.users.update_one(
                {"_id": ObjectId(user['_id'])},
                {"$push": {"groups": ObjectId(group['_id'])}}
            )
            updated_user = mongo.db.users.find_one({"_id": ObjectId(user['_id'])})
            print(f"Group {group['_id']} added to user {user['_id']}. Updated user: {updated_user}")
        else:
            # Create a new group with the user's major as the group name
            new_group = {
                'groupName': major,
                'groupDescription': f'Group for {major} majors',
                'createdBy': username,
                'users': [ObjectId(user['_id'])],
                'project_content': {},
                'comment_json': {'General Discussion': []},  # Initialize as an array
                'projects': [],
                'created_at': datetime.datetime.utcnow(),
            }
            group_insert_result = mongo.db.groups.insert_one(new_group)
            group_id = group_insert_result.inserted_id

            # Debugging: Print the new group ID
            print(f"New group created with ID: {group_id}")

            # Add the new group to the user's groups field
            print(f"Before updating user's groups field: {user}")
            mongo.db.users.update_one(
                {"_id": ObjectId(result.inserted_id)},
                {"$push": {"groups": ObjectId(group_id)}}
            )
            updated_user = mongo.db.users.find_one({"_id": ObjectId(user['_id'])})
            print(f"Group {group_id} added to user {user['_id']}. Updated user: {updated_user}")

        response = jsonify({
            "message": "User registered successfully",
            "access_token": access_token,
            "new_user": user
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 201
    else:
        response = jsonify({'message': 'Email already exists'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 409





    

#Dependent frontend code: UserContext.js
@main_bp.route('/login', methods=['POST'])
def login():
    print('login')
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    user = mongo.db.users.find_one({"email": email})
    if not user or not check_password_hash(user['password'], password):
        return jsonify({"error": "Invalid email or password"}), 401
    user_details = get_user_context_details(user)
    user_details = {key: str(value) if isinstance(value, ObjectId) else value for key, value in user_details.items()}
    access_token = create_access_token(identity=user['username'], additional_claims=user_details)
    return jsonify(access_token=access_token), 200


#Dependent frontend code: StudentProfileEditor.js
@main_bp.route('/studentProfileEditor', methods=['GET', 'POST'])
@jwt_required()
def edit_student_profile():
    print('accessing studentProfileEditor route')
    username = get_jwt_identity()
    user = mongo.db.users.find_one({"username": username})
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    if request.method == 'POST':
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid data"}), 422
        
        update_data = {key: value for key, value in data.items() if key in {
            'username', 'email', 'university', 'interests', 'skills', 'biography', 
            'profile_photo', 'personal_website', 'resume', 
            'links', 'major', 'grad', 'github_link'
        }}
        
        if 'password' in update_data:
            update_data['password'] = generate_password_hash(update_data['password'])

        # Update the user in the database
        mongo.db.users.update_one({"username": username}, {"$set": update_data})
        user.update(update_data)
        if 'username' in update_data and update_data['username'] != username:
            user_details = get_user_context_details(user)
            user_details = {key: str(value) if isinstance(value, ObjectId) else value for key, value in user_details.items()}
            access_token = create_access_token(identity=update_data['username'], additional_claims=user_details)
        else:
            access_token = None

        return jsonify({
            'message': 'Profile updated successfully',
            'access_token': access_token
        }), 200
    
    user_details = get_user_details(user)
    portfolio = user_details.get('portfolio', [])
    project_ids = [ObjectId(project_id) for project_id in portfolio]
    projects = list(mongo.db.projects.find({"_id": {"$in": project_ids}}))
    user_details['portfolio'] = projects
    user_details = convert_objectid_to_str(user_details)
    return jsonify(user_details), 200




#Dependent frontend code: StudentProfileEditor.js


@main_bp.route('/massProjectPublish', methods=['POST'])
@jwt_required()
def massProjectPublish():
    username = get_jwt_identity()
    user = mongo.db.users.find_one({"username": username})

    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()
    if not data or 'selectedPortfolio' not in data:
        return jsonify({"error": "Invalid data"}), 422

    user_id = user['_id']

    project_ids = []
    for project in data['selectedPortfolio']:
        new_project = {
            'projectName': project.get('projectName', ''),
            'projectDescription': project.get('projectDescription', ''),
            'createdBy': username,
            'upvotes': [],
            'layers': [],
            'links': [],
            'created_at': datetime.datetime.utcnow(),
        }

        proj_insert_result = mongo.db.projects.insert_one(new_project)
        project_id = proj_insert_result.inserted_id
        project_ids.append(project_id)

    user_update_result = mongo.db.users.update_one(
        {"_id": user['_id']},
        {"$push": {"portfolio": {"$each": project_ids}}}
    )

    if user_update_result.modified_count == 0:
        return jsonify({"error": "Failed to update user portfolio"}), 500

    return jsonify({"message": "Projects published successfully"}), 200
    


@main_bp.route('/addBlocProject', methods=['POST'])
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



# Function to summarize text using OpenAI
def summarize_text_description_title_tags(text):
    try:
        print('Got to summarize_text_description_title_tags')
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content."},
                {"role": "user", "content": f"For the following file, please write a concise (less than 100 words) description for this project. Also, provide a list for suggested tags concerning general topics the file is about (tags like: machine learning, computer vision, NLP, robotics, genomics, etc). Lastly please provide a string name for this project. Please always format your response as a json with keys: name, tags, description. This is very important: the entirety of your response should constitute a valid JSON. There should be no json tags in the front or any leading/trailing text. Only give the json.  Here is the text:\n\n{text}"}            ],
            max_tokens=600,
            n=1,
            stop=None,
            temperature=0.5
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        print(f"Error summarizing text: {e}")
        return ""
    
# Function to summarize text using OpenAI
def summarize_text_layers(text):
    try:
        print('Got to summarize_text_layers')
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content."},
                {"role": "user", "content": f"I need to create a project page by summarizing the following text into multiple self-contained sections. Each section should be around 3 sentences. Make as many sections as necessary. These sections will explain the project in detail when viewed together. Please ensure that the entirety of your response is formatted as a valid JSON array with each paragraph as an object containing 'index' and 'content' keys. Do not include any additional text outside of the JSON array. There should be no json tags in the front or any leading/trailing text. Only give the json. THERE SHOULD BE NO: ```json in the response.   Here is the text:\n\n{text}"}
            ],
            max_tokens=600,
            n=1,
            stop=None,
            temperature=0.5
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        print(f"Error summarizing text: {e}")
        return ""

# Route for resume parsing
@main_bp.route('/projectFileParser', methods=['POST', 'OPTIONS'])
@cross_origin()
def projectFileParser():
    print('Opened the resume parser route')
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'}), 200
    data = request.get_json()
    if not data or 'fileText' not in data:
        return jsonify({'error': 'No fileText provided'}), 400
    file_text = data['fileText']
    try:
        surrounding_summary = summarize_text_description_title_tags(file_text)
        summary_content = summarize_text_layers(file_text)
        print(f'here is the summary_content: {summary_content}')
        return jsonify({'surrounding_summary': surrounding_summary, 'summary_content': summary_content}), 200
    except Exception as e:
        print(f"Error parsing proj file: {e}")
        return jsonify({'error': 'Failed to parse proj file'}), 500


@main_bp.route('/deleteProject', methods=['DELETE'])
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




@main_bp.route('/updateProject/<project_name>', methods=['POST'])
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


#Dependent frontend code: EditInPortfolio

@main_bp.route('/updateProject/<project_id>/<project_field>', methods=['POST'])
@jwt_required()
def update_project_by_id_field(project_id, project_field):
    username = get_jwt_identity()
    data = request.get_json()
    if not data or project_field not in data:
        return jsonify({"error": "Invalid data"}), 422
    user = mongo.db.users.find_one({"username": username})
    if not user:
        return jsonify({"error": "User not found"}), 404
    project = mongo.db.projects.find_one({"_id": ObjectId(project_id)})
    if not project:
        return jsonify({"error": "Project not found"}), 404
    if project['createdBy'] != username:
        return jsonify({"error": "Unauthorized action"}), 403
    mongo.db.projects.update_one(
        {"_id": ObjectId(project_id)},
        {"$set": {project_field: data[project_field]}}
    )
    updated_project = mongo.db.projects.find_one({"_id": ObjectId(project_id)})
    updated_project = convert_objectid_to_str(updated_project)
    return jsonify(updated_project), 200



@main_bp.route('/studentProfile', methods=['GET'])
@cross_origin(headers=['Content-Type','Authorization']) # Send Access-Control-Allow-Headers 
@jwt_required()
def student_profile():
    jwt_data = get_jwt()
    user_id = jwt_data.get('_id')
    print('here is the user_id, ', user_id)
    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    logging.debug(f"User found: {user}")

    if not user:
        response = jsonify({"error": "User not found"})
        response.status_code = 404
        return response
    
    portfolio = user.get('portfolio', [])
    project_ids = [ObjectId(project_id) for project_id in portfolio]
    logging.debug(f"Project IDs: {project_ids}")

    projects = list(mongo.db.projects.find({"_id": {"$in": project_ids}}))
    logging.debug(f"Projects found: {projects}")

    for project in projects:
        comment_ids = [ObjectId(comment_id) for comment_id in project.get('comments', [])]
        comments = list(mongo.db.comments.find({"_id": {"$in": comment_ids}}))
        for comment in comments:
            author = mongo.db.users.find_one({"_id": comment.get("author_id")})
            if author:
                comment["author"] = author["username"]
        comments = [convert_objectid_to_str(comment) for comment in comments]
        project["comments"] = comments
    projects = [convert_objectid_to_str(project) for project in projects]
    user_details = get_user_details(user)
    user_details['portfolio'] = projects
    user_details = convert_objectid_to_str(user_details)
    
    logging.debug(f"User details: {user_details}")

    return jsonify(user_details)


@main_bp.route('/handleComment/<username>', methods=['POST'])
@jwt_required()
def handle_comment(username):
    try:
        data = request.get_json()
        comment_author = data.get('author')
        comment_text = data.get('text')
        project_id = data.get('projectId')

        if not comment_author or not comment_text or not project_id:
            return jsonify({"error": "Author, text, and project ID are required"}), 400

        project = mongo.db.projects.find_one({"_id": ObjectId(project_id)})
        if not project:
            return jsonify({"error": "Project not found"}), 404

        author = mongo.db.users.find_one({"username": comment_author})
        if not author:
            return jsonify({"error": "Author not found"}), 404

        new_comment = {
            "_id": ObjectId(),  # Add the _id field here
            "author_id": author['_id'],
            "author": comment_author,
            "text": comment_text,
            "project_target": ObjectId(project_id),
            "upvotes": []
        }
        
        mongo.db.comments.insert_one(new_comment)
        mongo.db.projects.update_one(
            {"_id": ObjectId(project_id)},
            {"$push": {"comments": new_comment["_id"]}}
        )
        mongo.db.users.update_one(
            {"_id": author['_id']},
            {"$push": {"comments": new_comment["_id"]}}
        )

        project = mongo.db.projects.find_one({"_id": ObjectId(project_id)})
        comment_ids = project.get('comments', [])
        comments = list(mongo.db.comments.find({"_id": {"$in": comment_ids}}))
        project = convert_objectid_to_str(project)
        comments = [convert_objectid_to_str(comment) for comment in comments]

        return jsonify({"project": project, "comments": comments}), 200

    except Exception as e:
        print(f"Error occurred: {str(e)}")  # Log the error to the console
        return jsonify({"error": "An error occurred while handling the comment", "details": str(e)}), 500



#Dependent frontend: OrgFeed.js, GenDirectory.js

@main_bp.route('/genDirectory', methods=['GET'])
@jwt_required()
def get_directory_info():
    try:
        users = mongo.db.users.find()
        directory = [get_user_details(user) for user in users]
        return jsonify(convert_objectid_to_str(directory)), 200
    except Exception as e:
        print(f"Error fetching directory info: {e}")
        return jsonify({"error": "Unable to fetch directory info"}), 500


@main_bp.route('/userFilteredSearch/<value>', methods=['GET'])
@jwt_required()
def user_filtered_search(value):
    try:
        users = mongo.db.users.find({
            "$or": [
                {"username": {"$regex": value, "$options": "i"}},
                {"skills": {"$elemMatch": {"$regex": value, "$options": "i"}}},
                {"interests": {"$elemMatch": {"$regex": value, "$options": "i"}}},
                {"user_type": {"$regex": value, "$options": "i"}},
                {"email": {"$regex": value, "$options": "i"}},
                {"biography": {"$regex": value, "$options": "i"}}
            ]
        })
        directory = [get_user_feed_details(user) for user in users]
        response_data = convert_objectid_to_str(directory)
        return jsonify(response_data), 200
    except Exception as e:
        print(f"Error fetching directory info: {e}")
        return jsonify({"error": "Unable to fetch directory info"}), 500


@main_bp.route('/projectFilteredSearch/<value>', methods=['GET'])
@jwt_required()
def project_filtered_search(value):
    try:
        projects = mongo.db.projects.find({"$or": [
            {"createdBy": {"$regex": value, "$options": "i"}},
            {"projectName": {"$regex": value, "$options": "i"}},
            {"projectDescription": {"$regex": value, "$options": "i"}}
        ]})
        directory = [get_project_feed_details(project) for project in projects]
        response_data = convert_objectid_to_str(directory)
        return jsonify(response_data), 200
    except Exception as e:
        print(f"Error fetching directory info: {e}")
        return jsonify({"error": "Unable to fetch directory info"}), 500

#Dependent frontend: OtherStudentProfile.js

@main_bp.route('/profile/<username>', methods=['GET'])
@jwt_required()
def other_student_profile(username):
    user = mongo.db.users.find_one({"username": username})
    if not user:
        return jsonify({"error": "User not found"}), 404
    portfolio = user.get('portfolio', [])
    project_ids = [ObjectId(project_id) for project_id in portfolio]
    projects = list(mongo.db.projects.find({"_id": {"$in": project_ids}}))
    for project in projects:
        comment_ids = [ObjectId(comment_id) for comment_id in project.get('comments', [])]
        comments = list(mongo.db.comments.find({"_id": {"$in": comment_ids}}))
        for comment in comments:
            author = mongo.db.users.find_one({"_id": comment.get("author_id")})
            if author:
                comment["author"] = author["username"]
        comments = [convert_objectid_to_str(comment) for comment in comments]
        project["comments"] = comments
    projects = [convert_objectid_to_str(project) for project in projects]
    user_details = get_user_details(user)
    user_details['portfolio'] = projects
    user_details = convert_objectid_to_str(user_details)
    return jsonify(user_details), 200




@main_bp.route('/injectSampleData', methods=['POST'])
def inject_sample_data():
    for user in sample_users:
        if not mongo.db.users.find_one({"username": user["username"]}):
            mongo.db.users.insert_one(user)
    return jsonify({"message": "Sample data injected successfully"}), 201


@main_bp.route('/migrateProjects', methods=['POST'])
def migrate_projects():
    users = mongo.db.users.find()
    for user in users:
        portfolio = user.get('portfolio', [])
        new_portfolio = []
        user_comment_ids = []
        for project in portfolio:
            project_copy = copy.deepcopy(project)
            result = mongo.db.projects.insert_one( project_copy )
            project_id = result.inserted_id
            
            new_portfolio.append(str(project_id))
        mongo.db.users.update_one(
            {'_id': user['_id']},
            {'$set': {'portfolio': new_portfolio, 'comments': user_comment_ids}}
        )
    return jsonify({"message": "Projects and comments migrated successfully"}), 200


@main_bp.route('/populateLayers', methods=['POST'])
def populate_layers():
    specific_project_id = ObjectId("6691734f56d3f879b525f3e4")
    specific_project = mongo.db.projects.find_one({"_id": specific_project_id})
    layers_data = specific_project.get("layers", [])
    mongo.db.projects.update_many(
        {},
        {"$set": {"layers": layers_data}}
    )
    return jsonify({"message": "Layers field updated in all projects successfully"}), 200



#Dependent frontend: ProjectEntry.js
@main_bp.route('/upvoteProject', methods=['POST'])
@jwt_required()
def upvote_project():
    data = request.get_json()
    user_id = ObjectId(data.get('user_id'))
    project_id = ObjectId(data.get('project_id'))
    app.logger.info(f"Received upvote request: user_id={user_id}, project_id={project_id}")

    if not user_id:
        return jsonify({"error": "User_id is required"}), 400

    user = mongo.db.users.find_one({"_id": user_id})
    if not user:
        return jsonify({"error": "User not found"}), 404

    username = user.get('username')
    new_upvote = {
        "project_id": project_id,
        "user_id": user_id,
        "author": username,
    }
    result = mongo.db.upvotes.insert_one(new_upvote)
    if not result.acknowledged:
        app.logger.error("Failed to insert new upvote")
        return jsonify({"error": "Failed to insert new upvote"}), 500

    new_upvote_id = result.inserted_id

    update_project = mongo.db.projects.update_one(
        {'_id': project_id},
        {"$addToSet": {"upvotes": new_upvote_id}}
    )

    if update_project.modified_count == 0:
        return jsonify({"error": "Project not updated"}), 404

    updated = mongo.db.users.update_one(
        {"_id": user_id},
        {"$addToSet": {"upvotes": new_upvote_id}}
    )

    if updated.modified_count == 0:
        return jsonify({"error": "User not updated"}), 404

    new_upvote["_id"] = str(new_upvote_id)
    new_upvote["project_id"] = str(new_upvote["project_id"])
    new_upvote["user_id"] = str(new_upvote["user_id"])

    app.logger.info(f"Upvote successful: {new_upvote}")
    return jsonify(new_upvote), 200

@main_bp.route('/api/notifications')
@jwt_required()
def get_notifications():
    username = get_jwt_identity()
    user = mongo.db.users.find_one({"username": username})
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    notifications = mongo.db.notifications.find(
        {"user_id": user['_id'], "is_read": False}
    ).sort("created_at", -1).limit(10)
    
    return jsonify([
        {
            'id': str(n['_id']),
            'type': n['type'],
            'message': n['message'],
            'created_at': n['created_at'].isoformat()
        } for n in notifications
    ]), 200

@main_bp.route('/api/notifications/mark_read/<notification_id>', methods=['POST'])
@jwt_required()
def mark_notification_read(notification_id):
    username = get_jwt_identity()
    user = mongo.db.users.find_one({"username": username})
    if not user:
        return jsonify({"error": "User not found"}), 404

    result = mongo.db.notifications.update_one(
        {"_id": ObjectId(notification_id), "user_id": user['_id']},
        {"$set": {"is_read": True}}
    )
    if result.modified_count > 0:
        return jsonify({'success': True}), 200
    else:
        return jsonify({'success': False, 'message': 'Notification not found or already read'}), 404

@main_bp.route('/api/create_notification', methods=['POST'])
@jwt_required()
def create_notification():
    username = get_jwt_identity()
    user = mongo.db.users.find_one({"username": username})
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()
    new_notification = {
        'user_id': user['_id'],
        'type': data['type'],
        'message': data['message'],
        'created_at': datetime.datetime.utcnow(),
        'is_read': False
    }
    result = mongo.db.notifications.insert_one(new_notification)
    return jsonify({'success': True, 'id': str(result.inserted_id)}), 201




#Dependent frontend: RankedFeed.js, TagsFeed.js

@main_bp.route('/returnFeed', methods=['GET'])
@jwt_required()
def returnFeed():
    username = get_jwt_identity()
    projects = list(mongo.db.projects.find())

    for project in projects:
        comment_ids = [ObjectId(comment_id) for comment_id in project.get('comments', [])]
        comments = list(mongo.db.comments.find({"_id": {"$in": comment_ids}}))
        comments = [convert_objectid_to_str(comment) for comment in comments]
        project["comments"] = comments
    projects = [convert_objectid_to_str(project) for project in projects]

    return json_util.dumps(projects), 200 



@main_bp.route('/returnProjects', methods=['POST'])
@jwt_required()
def return_projects():
    username = get_jwt_identity()
    data = request.get_json()
    projects = []
    for upvote_id in data:
        upvote_obj_id = ObjectId(upvote_id)
        upvote = mongo.db.upvotes.find_one({"_id": upvote_obj_id})
        project = mongo.db.projects.find_one({"_id": ObjectId(upvote["project_id"])})
        if project:
            projects.append(project)
    projects = [convert_objectid_to_str(project) for project in projects]
    return json_util.dumps(projects), 200



if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    app.run(debug=True, port=5000)




