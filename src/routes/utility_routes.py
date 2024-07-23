


from flask import Blueprint, request, jsonify, send_from_directory
from flask import current_app as app
from flask_jwt_extended import jwt_required
from .. import mongo
from ..fake_data import sample_users
import copy
from bson import json_util, ObjectId
from flask_cors import cross_origin
import datetime
import openai
import uuid
import hashlib


utility_bp = Blueprint('utility', __name__)

@utility_bp.route('/injectSampleData', methods=['POST'])
def inject_sample_data():
    for user in sample_users:
        if not mongo.db.users.find_one({"username": user["username"]}):
            mongo.db.users.insert_one(user)
    return jsonify({"message": "Sample data injected successfully"}), 201

@utility_bp.route('/migrateProjects', methods=['POST'])
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


@utility_bp.route('/populateLayers', methods=['POST'])
def populate_layers():
    specific_project_id = ObjectId("6691734f56d3f879b525f3e4")
    specific_project = mongo.db.projects.find_one({"_id": specific_project_id})
    layers_data = specific_project.get("layers", [])
    mongo.db.projects.update_many(
        {},
        {"$set": {"layers": layers_data}}
    )
    return jsonify({"message": "Layers field updated in all projects successfully"}), 200

@utility_bp.route('/upvoteProject', methods=['POST'])
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

@utility_bp.route('/resumeParser', methods=['POST', 'OPTIONS'])
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

@utility_bp.route('/projectFileParser', methods=['POST', 'OPTIONS'])
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

@utility_bp.route('/createAccessKey', methods=['POST'])
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

@utility_bp.route('/checkAccessKey', methods=['POST'])
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

@utility_bp.route('/joinWaitingList', methods=['POST'])
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


@utility_bp.route('/')
def hello():
    return 'This 1 Message Means that heroku is running correctly!'

@utility_bp.route('/static/<path:path>', methods=['GET'])
def send_static(path):
    return send_from_directory('src/static/images', path)


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

