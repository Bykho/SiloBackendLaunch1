


from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from bson import json_util, ObjectId
from .. import mongo
from ..routes_schema_utility import get_user_details, get_user_context_details, get_user_feed_details, get_portfolio_details, get_project_feed_details, convert_objectid_to_str
from .pinecone_utils import * 


feed_bp = Blueprint('feed', __name__)
pinecone_index = initialize_pinecone()

@feed_bp.route('/returnFeed', methods=['POST'])
@jwt_required()
def returnFeed():
    username = get_jwt_identity()
    data = request.get_json()

    # Get pagination parameters from the request
    page = int(data.get('page', 1))
    per_page = int(data.get('per_page', 10))

    # Calculate skip value for pagination
    skip = (page - 1) * per_page

    # Query the database with pagination and sorting
    projects = list(mongo.db.projects.find()
                    .sort('created_at', -1)  # Sort by created_at in descending order
                    .skip(skip)
                    .limit(per_page))

    # Process comments for each project
    for project in projects:
        comment_ids = [ObjectId(comment_id) for comment_id in project.get('comments', [])]
        comments = list(mongo.db.comments.find({"_id": {"$in": comment_ids}}))
        comments = [convert_objectid_to_str(comment) for comment in comments]
        project["comments"] = comments

    # Convert ObjectId to string for JSON serialization
    projects = [convert_objectid_to_str(project) for project in projects]

    # Get total count of projects for pagination info
    total_projects = mongo.db.projects.count_documents({})
    total_pages = (total_projects + per_page - 1) // per_page

    # Prepare response
    response = {
        "projects": projects,
        "page": page,
        "per_page": per_page,
        "total_projects": total_projects,
        "total_pages": total_pages
    }

    return json_util.dumps(response), 200


@feed_bp.route('/popularFeed', methods=['POST'])
@jwt_required()
def popularFeed():
    username = get_jwt_identity()
    data = request.get_json()

    page = int(data.get('page', 1))
    per_page = int(data.get('per_page', 10))
    skip = (page - 1) * per_page

    pipeline = [
        {
            "$facet": {
                "totalCount": [
                    {"$count": "count"}
                ],
                "paginatedResults": [
                    {"$addFields": {"upvotesLength": {"$size": "$upvotes"}}},
                    {"$sort": {"upvotesLength": -1}},
                    {"$skip": skip},
                    {"$limit": per_page},
                    {"$project": {"upvotesLength": 0}}
                ]
            }
        }
    ]

    result = list(mongo.db.projects.aggregate(pipeline))[0]
    
    total_projects = result['totalCount'][0]['count'] if result['totalCount'] else 0
    projects = result['paginatedResults']

    # Process comments for each project
    for project in projects:
        comment_ids = [ObjectId(comment_id) for comment_id in project.get('comments', [])]
        comments = list(mongo.db.comments.find({"_id": {"$in": comment_ids}}))
        comments = [convert_objectid_to_str(comment) for comment in comments]
        project["comments"] = comments

    projects = [convert_objectid_to_str(project) for project in projects]

    total_pages = (total_projects + per_page - 1) // per_page

    response = {
        "projects": projects,
        "page": page,
        "per_page": per_page,
        "total_projects": total_projects,
        "total_pages": total_pages
    }

    return json_util.dumps(response), 200


@feed_bp.route('/returnProjects', methods=['POST'])
@jwt_required()
def return_projects():
    username = get_jwt_identity()
    data = request.get_json()
    
    if isinstance(data, dict) and 'page' in data:
        # Handle paginated request
        page = int(data.get('page', 1))
        per_page = int(data.get('per_page', 10))
        skip = (page - 1) * per_page
        
        upvotes = mongo.db.upvotes.find({"user_id": username}).skip(skip).limit(per_page)
        project_ids = [ObjectId(upvote["project_id"]) for upvote in upvotes]
        projects = list(mongo.db.projects.find({"_id": {"$in": project_ids}}))
        
        total_upvotes = mongo.db.upvotes.count_documents({"user_id": username})
        total_pages = (total_upvotes + per_page - 1) // per_page
        
        response = {
            "projects": [convert_objectid_to_str(project) for project in projects],
            "page": page,
            "per_page": per_page,
            "total_projects": total_upvotes,
            "total_pages": total_pages
        }
    else:
        # Handle array of upvote IDs
        projects = []
        for upvote_id in data:
            try:
                upvote_obj_id = ObjectId(upvote_id)
                upvote = mongo.db.upvotes.find_one({"_id": upvote_obj_id})
                if upvote:
                    project = mongo.db.projects.find_one({"_id": ObjectId(upvote["project_id"])})
                    if project:
                        projects.append(project)
            except InvalidId:
                print(f"Invalid upvote ID: {upvote_id}")
                continue
        
        response = [convert_objectid_to_str(project) for project in projects]

    return json_util.dumps(response), 200


@feed_bp.route('/searchProjects', methods=['POST'])
@jwt_required()
def search_projects():
    try:
        # Get the search query from the request
        data = request.get_json()
        search_text = data.get('query', '')

        # Use the $search operator to query the Atlas Search index
        search_query = {
            "$search": {
                "index": "projectSearch",  # Name of the search index you created
                "text": {
                    "query": search_text,
                    "path": ["projectName", "projectDescription", "tags", "createdBy", "layers.value"]
                }
            }
        }

        # Perform the search query
        projects = list(mongo.db.projects.aggregate([search_query]))

        # Process the results (e.g., convert ObjectIds to strings)
        projects = [convert_objectid_to_str(project) for project in projects]

        # Return the results as JSON
        return jsonify({"projects": projects}), 200

    except Exception as e:
        print(f"Error searching projects: {e}")
        return jsonify({"error": "Unable to perform search"}), 500




@feed_bp.route('/genDirectory', methods=['GET'])
@jwt_required()
def get_directory_info():
    try:
        users = mongo.db.users.find()
        directory = [get_user_details(user) for user in users]
        return jsonify(convert_objectid_to_str(directory)), 200
    except Exception as e:
        print(f"Error fetching directory info: {e}")
        return jsonify({"error": "Unable to fetch directory info"}), 500

@feed_bp.route('/userFilteredSearch/<value>', methods=['GET'])
@jwt_required()
def user_filtered_search(value):
    try:
        if value.strip() == "" or value == 'all' or value == None:  # Check if value is empty or just spaces
            users = mongo.db.users.find()
        else: 
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

@feed_bp.route('/projectFilteredSearch/<value>', methods=['GET'])
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
    

@feed_bp.route('/updateProjectEmbeddings', methods=['POST'])
@jwt_required()
def update_project_embeddings():
    projects = mongo.db.projects.find()
    
    for project in projects:
        project_content = f"{project['projectName']} {project['projectDescription']} {' '.join(project.get('tags', []))}"
        project_embedding = get_embedding(project_content)
        upsert_vector(pinecone_index, str(project['_id']), project_embedding, metadata={"type": "project", "project_id": str(project['_id'])})
    
    return jsonify({"message": "Project embeddings updated successfully"}), 200


@feed_bp.route('/getPersonalizedFeed', methods=['GET'])
@jwt_required()
def get_personalized_feed():
    print('got to personalized feed')
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')
    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    user_embedding = get_or_create_user_embedding(pinecone_index, user)
    
    similar_projects = query_similar_vectors_projects(pinecone_index, user_embedding, top_k=15)
    print(similar_projects, "similar_projects!")
    project_ids = []
    for match in similar_projects:
        metadata = match.get('metadata', {})
        if metadata.get('type') == 'project':
            project_id = metadata.get('project_id')
            if project_id:
                try:
                    project_ids.append(ObjectId(project_id))
                except:
                    print(f"Invalid project_id: {project_id}")
    
    projects = list(mongo.db.projects.find({"_id": {"$in": project_ids}}))
    
    for project in projects:
        comment_ids = [ObjectId(comment_id) for comment_id in project.get('comments', [])]
        comments = list(mongo.db.comments.find({"_id": {"$in": comment_ids}}))
        comments = [convert_objectid_to_str(comment) for comment in comments]
        project["comments"] = comments
    
    projects = [convert_objectid_to_str(project) for project in projects]    
    return json_util.dumps(projects), 200


@feed_bp.route('/updateUserEmbedding', methods=['POST'])
@jwt_required()
def update_user_embedding():
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')
    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    get_or_create_user_embedding(pinecone_index, user)
    
    return jsonify({"message": "User embedding updated successfully"}), 200

@feed_bp.route('/returnPersonalizedFeed', methods=['GET'])
@jwt_required()
def return_personalized_feed():
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')
    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    user_embedding = get_or_create_user_embedding(pinecone_index, user)
    
    similar_projects = query_similar_vectors_projects(pinecone_index, user_embedding, top_k=20)
    
    project_ids = [ObjectId(match['metadata']['project_id']) for match in similar_projects]
    projects = list(mongo.db.projects.find({"_id": {"$in": project_ids}}))
    
    for project in projects:
        comment_ids = [ObjectId(comment_id) for comment_id in project.get('comments', [])]
        comments = list(mongo.db.comments.find({"_id": {"$in": comment_ids}}))
        comments = [convert_objectid_to_str(comment) for comment in comments]
        project["comments"] = comments
    
    projects = [convert_objectid_to_str(project) for project in projects]
    
    return json_util.dumps(projects), 200




