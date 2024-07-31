

from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
from .. import mongo
from ..routes_schema_utility import get_user_details, get_user_context_details, get_user_feed_details, get_portfolio_details, get_project_feed_details, get_project_details, convert_objectid_to_str
import datetime
from flask_cors import cross_origin
import logging



user_bp = Blueprint('user', __name__)

@user_bp.route('/getUsersByIds', methods=['POST'])
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

@user_bp.route('/profile/<username>', methods=['GET'])
@jwt_required()
def other_student_profile(username):
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')
    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    print('username from get_jwt: ', user.get('username'))
    username = user.get('username')

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

@user_bp.route('/SignUp', methods=['POST', 'OPTIONS'])
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
        data['shared'] = False
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

@user_bp.route('/toggleShareProfile', methods=['POST'])
@jwt_required()
def toggle_share_profile():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        if not user_id:
            return jsonify({"message": "User ID is required"}), 400
        user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
        if user:
            mongo.db.users.update_one({"_id": user['_id']}, {"$set": {"shared": True}})
            return jsonify({"message": "Profile share status updated", "shared": True}), 200
        else:
            return jsonify({"message": "User not found"}), 404
    except Exception as e:
        return jsonify({"message": str(e)}), 500


@user_bp.route('/public/<username>/<user_id>', methods=['GET'])
def get_public_profile(username, user_id):
    try:
        user = mongo.db.users.find_one({"_id": ObjectId(user_id), "shared": True})
        if user:
            user_data = get_user_details(user)
            return jsonify(user_data), 200
        else:
            return jsonify({"message": "User not found or profile not shared"}), 404
    except Exception as e:
        return jsonify({"message": str(e)}), 500
    

@user_bp.route('/login', methods=['POST'])
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

@user_bp.route('/studentProfileEditor', methods=['GET', 'POST'])
@jwt_required()
def edit_student_profile():
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')
    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    print('username from get_jwt: ', user.get('username'))
    username = user.get('username')

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

@user_bp.route('/studentProfile', methods=['GET'])
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



@user_bp.route('/massProjectPublish', methods=['POST'])
@jwt_required()
def massProjectPublish():
    jwt_claims = get_jwt()
    username = jwt_claims.get('username')
    print('Username from JWT:', username)
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

