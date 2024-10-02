

from flask import Blueprint, request, jsonify, send_file, render_template
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
from .. import mongo, mail
from ..routes_schema_utility import get_user_details, get_user_context_details, get_user_feed_details, get_portfolio_details, get_project_feed_details, get_project_details, convert_objectid_to_str
import datetime
from flask_cors import cross_origin
import logging
from flask_mail import Message
from ..routes.mixpanel_utils import track_event, set_user_profile
from .pinecone_utils import initialize_pinecone, get_embedding, upsert_vector
import datetime
import random
import string
import json
import io
import base64
from .resend_utils import resend_bp, send_email
import resend



user_bp = Blueprint('user', __name__)
pinecone_index = initialize_pinecone()


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

@user_bp.route('/profile/<id>', methods=['GET'])
@jwt_required()
def other_student_profile(id):
    try:
        user_id = ObjectId(id)
    except Exception as e:
        return jsonify({"error": "Invalid user ID"}), 400
    
    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})

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
        data['scores'] = []
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

        response = jsonify({
            "message": "User registered successfully",
            "access_token": access_token,
            "new_user": user
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        track_event(str(user['_id']), 'signup', {'email': email, 'time': datetime.datetime.utcnow()})
        set_user_profile(str(user['_id']), {'name': str(user['username']), 'email': str(user['email']), 'signup time': datetime.datetime.utcnow()})
        send_welcome_email(email, username)
        return response, 201
    else:
        response = jsonify({'message': 'Email already exists'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 409

def send_welcome_email(to_email, username):
    email_data = {
        'username': username,
    }
    html_content = render_template('welcome_email.html', **email_data)
    
    r = resend.Emails.send({
        "from": 'Dan Ringness <dan@silorepo.com>',
        "to": to_email,
        "subject": "Welcome to Silo!",
        "html": html_content
    })

    return "Welcome email sent successfully!"

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
            portfolio = user.get('portfolio', [])
            project_ids = [ObjectId(project_id) for project_id in portfolio]
            projects = list(mongo.db.projects.find({"_id": {"$in": project_ids}}))
            
            for project in projects:
                # Assuming comments should be excluded for public profile
                project["comments"] = []  # Clear comments for public profile

            projects = [convert_objectid_to_str(project) for project in projects]
            user_data = get_user_details(user)
            user_data['portfolio'] = projects
            user_data = convert_objectid_to_str(user_data)

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

    track_event(str(user['_id']), 'login', {'email': email, 'time': datetime.datetime.utcnow()})
    set_user_profile(str(user['_id']), {'name': user['username'], 'email': user['email'], 'last_login': datetime.datetime.utcnow()})
    return jsonify(access_token=access_token), 200

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@user_bp.route('/studentProfileEditor', methods=['GET', 'POST'])
@jwt_required()
def edit_student_profile():
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')
    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    
    if not user:
        return jsonify({"error": "User not found"}), 404

    username = user.get('username')
    print('username from get_jwt:', username)

    if request.method == 'POST':
        # Check if the request is FormData (Content-Type: multipart/form-data)
        if request.content_type.startswith('multipart/form-data'):
            data = request.form.to_dict()
            # Convert JSON fields back from string if needed (e.g., interests, skills)
            data['interests'] = json.loads(data['interests']) if 'interests' in data else []
            data['skills'] = json.loads(data['skills']) if 'skills' in data else []
            data['papers'] = json.loads(data['papers']) if 'papers' in data else []
            data['links'] = json.loads(data['links']) if 'links' in data else []
            # Handle the resume file if uploaded
            if 'resume' in request.files:
                file = request.files['resume']
                if file and allowed_file(file.filename):
                    # Read the file and encode it as base64
                    file_content = file.read()
                    encoded_content = base64.b64encode(file_content).decode('utf-8')
                    
                    # Create the data URL
                    mime_type = file.content_type or 'application/pdf'  # Default to PDF if mime type is not available
                    data['resume'] = f"data:{mime_type};base64,{encoded_content}"
                else:
                    return jsonify({"error": "Invalid file type"}), 400
        else:
            data = request.get_json()
        
        if not data:
            return jsonify({"error": "Invalid data"}), 422

        # Only update fields that are allowed
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

        # Generate a new access token if the username is updated
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
    
    # Handle GET request to fetch user details
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
            'user_id': str(user_id),
            'created_at': datetime.datetime.utcnow(),
            'visibility': project.get('visibility', True)
        }

        proj_insert_result = mongo.db.projects.insert_one(new_project)
        project_id = proj_insert_result.inserted_id
        project_ids.append(project_id)

        # Add embeddings for each project
        project_id_str = str(project_id)
        new_project["_id"] = project_id_str
        new_project = convert_objectid_to_str(new_project)

        # Create embedding for the project
        project_content = f"{new_project['projectName']} {new_project['projectDescription']} {' '.join(new_project.get('tags', []))}"
        project_embedding = get_embedding(project_content)
        upsert_vector(pinecone_index, project_id_str, project_embedding, metadata={"type": "project", "project_id": project_id_str})

    user_update_result = mongo.db.users.update_one(
        {"_id": user['_id']},
        {"$push": {"portfolio": {"$each": project_ids}}}
    )

    if user_update_result.modified_count == 0:
        return jsonify({"error": "Failed to update user portfolio"}), 500

    return jsonify({"message": "Projects published successfully"}), 200


@user_bp.route('/getUserUpvotes', methods=['POST'])
@jwt_required()
def get_user_upvotes():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        if not user_id:
            return jsonify({"message": "User ID is required"}), 400

        user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            return jsonify({"message": "User not found"}), 404

        upvotes = user.get('upvotes', [])
        print('GETUSERUPVOTES here is the upvotes array: ', convert_objectid_to_str(upvotes))
        return jsonify({"upvotes": convert_objectid_to_str(upvotes)}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500






@user_bp.route('/send-test-email', methods=['POST'])
def send_test_email():
    data = request.get_json()
    recipient_email = data.get('email')
    print('recipient_email: ', recipient_email)
    if not recipient_email:
        return jsonify({"message": "Email is required"}), 400

    try:
        msg = Message(subject="Test Email",
                      sender=mail.sender,  # Use mail.sender to get the default sender
                      recipients=[recipient_email])
        msg.body = "This is a test email sent from Flask app."
        mail.send(msg)
        return jsonify({"message": "Test email sent to " + recipient_email}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500


@user_bp.route('/send-reset-code', methods=['POST'])
def send_reset_code():
    data = request.get_json()
    email = data.get('email')
    
    user = mongo.db.users.find_one({"email": email})
    if not user:
        return jsonify({"message": "Email not found"}), 404

    reset_code = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
    expiration_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=30)

    mongo.db.retrieval_codes.insert_one({
        "email": email,
        "reset_code": reset_code,
        "expires_at": expiration_time
    })

    msg = Message(subject="Password Reset Code",
                  sender=mail.sender,  # Use mail.sender to get the default sender
                  recipients=[email])
    msg.body = f"Your password reset code is: {reset_code}. This code will expire in 30 minutes."
    mail.send(msg)

    return jsonify({"message": "Reset code sent"}), 200

@user_bp.route('/verify-reset-code', methods=['POST'])
def verify_reset_code():
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')

    reset_entry = mongo.db.retrieval_codes.find_one({"email": email, "reset_code": code})

    if not reset_entry:
        return jsonify({"message": "Invalid code"}), 400

    if reset_entry['expires_at'] < datetime.datetime.utcnow():
        return jsonify({"message": "Code expired"}), 400

    return jsonify({"message": "Code verified"}), 200

@user_bp.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')
    new_password = data.get('newPassword')

    reset_entry = mongo.db.retrieval_codes.find_one({"email": email, "reset_code": code})

    if not reset_entry:
        return jsonify({"message": "Invalid code"}), 400

    if reset_entry['expires_at'] < datetime.datetime.utcnow():
        return jsonify({"message": "Code expired"}), 400

    hashed_password = generate_password_hash(new_password)
    mongo.db.users.update_one({"email": email}, {"$set": {"password": hashed_password}})

    mongo.db.retrieval_codes.delete_one({"email": email, "reset_code": code})

    return jsonify({"message": "Password reset successfully"}), 200



@user_bp.route('/notifications', methods=['GET'])
@jwt_required()
@cross_origin()
def get_notifications():
    print('notifications is getting run')
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')
    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})

    if not user:
        return jsonify({"error": "User not found"}), 404
    
    notifications_cursor = mongo.db.notifications.find(
        {"recipient_id": str(user_id), "is_read": False}
    ).sort("created_at", -1).limit(10)
    
    notifications = list(notifications_cursor)  # Convert cursor to a list
    print('NOTIFICATIONS notifications:', notifications)

    return jsonify([
        {
            'id': str(n['_id']),
            'type': n['type'],
            'message': n['message'],
            'project_name': n['project_name'],
            'from_user': n['from_user'],
            'created_at': n['created_at'].isoformat()
        } for n in notifications
    ]), 200

@user_bp.route('/notifications_mark_read/<notification_id>', methods=['POST'])
@jwt_required()
@cross_origin()
def mark_notification_read(notification_id):
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')
    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        return jsonify({"error": "User not found"}), 404

    result = mongo.db.notifications.update_one(
        {"_id": ObjectId(notification_id), "recipient_id": str(user_id)},
        {"$set": {"is_read": True}}
    )
    if result.modified_count > 0:
        return jsonify({'success': True}), 200
    else:
        return jsonify({'success': False, 'message': 'Notification not found or already read'}), 404

@user_bp.route('/create_notification', methods=['POST'])
@jwt_required()
@cross_origin()
def create_notification():
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')
    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()
    new_notification = {
        'user_id': ObjectId(user_id),
        'type': data['type'],
        'message': data['message'],
        'project_name': data['project_name'],
        'from_user': data['from_user'],
        'created_at': datetime.datetime.utcnow(),
        'is_read': False,
        'project_id': data['project_id'],
        'recipient_id': data['recipient_id']
    }
    result = mongo.db.notifications.insert_one(new_notification)
    return jsonify({'success': True, 'id': str(result.inserted_id)}), 201


