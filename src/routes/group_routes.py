

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from bson import ObjectId, errors
from bson.objectid import InvalidId
from .. import mongo
import datetime
from ..routes_schema_utility import get_user_details, get_user_context_details, get_user_feed_details, get_portfolio_details, get_project_feed_details, convert_objectid_to_str

group_bp = Blueprint('group', __name__)

@group_bp.route('/joinGroup', methods=['POST'])
@jwt_required()
def join_group():
    #print('entered the /joinGroup route')
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')
    #print('User ID from JWT:', user_id)
    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    #print('here is the user: ', user)
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    data = request.get_json()
    #print('here is the data: ', data)
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


@group_bp.route('/groupCreate', methods=['POST'])
@jwt_required()
def groupCreate():
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')
    print('User ID from JWT:', user_id)
    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})

    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()
    if not data or 'groupName' not in data or 'groupDescription' not in data:
        return jsonify({"error": "Invalid data"}), 422

    new_group = {
        'groupName': data['groupName'],
        'groupDescription': data['groupDescription'],
        'createdBy': user_id,
        'users': [],
        'project_content': data['groupProject_Content'],
        'projects': [],
        'comment_json': {'General Discussion': []},  # Initialize as an array
        'created_at': datetime.datetime.utcnow(),
        'bounties': [],
    }

    group_insert_result = mongo.db.groups.insert_one(new_group)
    group_id = group_insert_result.inserted_id

    return jsonify({"message": "Group created successfully", "group_id": str(group_id)}), 200



@group_bp.route('/returnGroups', methods=['GET'])
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
                "bounties": group.get("bounties", []),
                "created_at": group["created_at"],
                "projects": [str(project_id) for project_id in group.get("projects", [])]  # Convert project ObjectId to string
            })
        group_list = convert_objectid_to_str(group_list)
        return jsonify(group_list), 200
    except Exception as e:
        print(f"Error fetching groups: {e}")
        return jsonify({"error": "Failed to fetch groups"}), 500
    

@group_bp.route('/returnMyGroups', methods=['GET'])
@jwt_required()
def returnMyGroups():
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')
    print('User ID from JWT:', user_id)
    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
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
                "bounties": group.get("bounties", []),
                "projects": [str(project_id) for project_id in group.get("projects", [])]  # Convert project ObjectId to string
            })
        print('/RETURNMYGROUPS here is groups_to_be_returned: ', groups_to_be_returned)
        groups_to_be_returned = convert_objectid_to_str(groups_to_be_returned)
        return jsonify(groups_to_be_returned), 200
    except Exception as e:
        print(f"Error fetching groups: {e}")
        return jsonify({"error": "Failed to fetch groups"}), 500

    

@group_bp.route('/saveProjectToGroup', methods=['POST'])
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

@group_bp.route('/updateCommentJson', methods=['POST'])
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


@group_bp.route('/getBountiesByIds', methods=['POST'])
@jwt_required()
def get_bounties_by_ids():
    data = request.get_json()
    bounty_ids = data.get('bounties')
    if not bounty_ids:
        return jsonify({"error": "Bounty IDs are required"}), 400

    try:
        bounty_ids = [ObjectId(bounty_id) for bounty_id in bounty_ids]
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    try:
        bounties = mongo.db.bounties.find({"_id": {"$in": bounty_ids}})
        bounty_list = []
        for bounty in bounties:
            bounty_list.append({
                "_id": str(bounty["_id"]),
                "author": bounty.get("author", ""),
                "text": bounty.get("text", ""),
                "project_links": bounty.get("project_links", ""),
                "group_target": str(bounty.get("group_target", "")),
                "upvotes": [str(upvote_id) for upvote_id in bounty.get("upvotes", [])],
            })
        return jsonify(bounty_list), 200
    except Exception as e:
        return jsonify({"error": f"Error fetching comments: {e}"}), 500

@group_bp.route('/handleGroupBountyPost', methods=['POST'])
@jwt_required()
def handle_group_bounty_post():
    try:
        data = request.get_json()
        bounty_text = data.get('text')
        group_id = data.get('groupId')
        title = data.get('title', 'n/a')
        project_links = data.get('project_links', [])

        print()
        print()
        print('/HANDLEGROUPBOUNTYPOST: bounty_text, ', bounty_text)
        print('/HANDLEGROUPBOUNTYPOST: group_id, ', group_id)
        print('/HANDLEGROUPBOUNTYPOST: title, ', title)

        if not bounty_text or not group_id or not title:
            return jsonify({"error": "Text, group ID, and title are required"}), 400
        
        group = mongo.db.groups.find_one({"_id": ObjectId(group_id)})
        if not group:
            return jsonify({"error": "Group not found"}), 404
    
        print('HANDLEGROUPBOUNTYPOST group name: ', group["groupName"])
    
        user = mongo.db.users.find_one({"username": get_jwt_identity()})
        if not user:
            return jsonify({"error": "User not found"}), 404      

        new_bounty = {
            "author_id": user['_id'],
            "author": user['username'],
            "title": title,
            "text": bounty_text,
            "group_target": ObjectId(group_id),
            "upvotes": [],
            "responses": [],
            "project_links": project_links
        }

        # Insert the new bounty into the bounties collection
        result = mongo.db.bounties.insert_one(new_bounty)

        # Retrieve the automatically generated ID from the insert operation
        new_bounty_id = result.inserted_id

        # Update group's bounties field (just add the bounty ID to the bounties array)
        mongo.db.groups.update_one(
            {"_id": ObjectId(group_id)},
            {"$push": {"bounties": new_bounty_id}}
        )

        # Update user's bounties field
        mongo.db.users.update_one(
            {"_id": user['_id']},
            {"$push": {"bounties": new_bounty_id}}
        )
        # Fetch updated comments
        updated_group = mongo.db.groups.find_one({"_id": ObjectId(group_id)})
        updated_bounties = [str(bounty_id) for bounty_id in updated_group['bounties']]
        return jsonify({"message": "Successfully added bounty", "newBounty": convert_objectid_to_str(new_bounty)}), 200
    except Exception as e:
        print(f"Error handling group bounty: {e}")
        return jsonify({"error": "Failed to handle bounty"}), 500
    

@group_bp.route('/getBountyResponses', methods=['POST'])
@jwt_required()
def get_bounty_responses():
    print('getBountyResponses')
    data = request.get_json()
    bounty_id = data.get('bountyId')

    if not bounty_id:
        return jsonify({"error": "Bounty ID is required"}), 400

    try:
        bounty = mongo.db.bounties.find_one({"_id": ObjectId(bounty_id)})
        print('bounty: ', bounty["responses"][0]["text"])
        if not bounty:
            return jsonify({"error": "Bounty not found"}), 404
        
        # Retrieve and return the responses
        responses = bounty.get('responses', [])

        # Convert ObjectId and datetime fields to strings
        for response in responses:
            response['author_id'] = str(response['author_id'])
            response['bounty_id'] = str(response['bounty_id'])
            response['date'] = response['date'].isoformat()

        for response in responses:
            print('response: ', response["text"])

        return jsonify(responses), 200

    except Exception as e:
        return jsonify({"error": f"Error fetching responses: {e}"}), 500


#USE USERID FOR LOOKUP.
@group_bp.route('/addBountyResponse', methods=['POST'])
@jwt_required()
def add_bounty_response():
    print()
    print()
    data = request.get_json()
    bounty_id = data.get('bountyId')
    author_id = data.get("author_id")
    response_text = data.get('text')

    print('bounty_id: ', bounty_id)
    print('author_id: ', author_id)
    print('response_text: ', response_text)

    if not bounty_id or not response_text:
        return jsonify({"error": "Bounty ID and response text are required"}), 400

    try:
        print('got to right before the mongo.db.users.find_one in addbountyresponse')
        user = mongo.db.users.find_one({"_id": ObjectId(author_id)})
        print('hello')
        print('user.username: ', user["username"])

        if not user:
            return jsonify({"error": "User not found"}), 404

        print('got to before bounty search')
        print('here is bounty_id: ', bounty_id)
        print('here is bounty_id type: ', type(bounty_id))

        try:
            bounty_object_id = ObjectId(bounty_id)
        except InvalidId as e:
            print(f"Invalid ObjectId: {e}")
            return jsonify({"error": "Invalid Bounty ID"}), 400
        
        print('here is the type for bounty_object_id: ', type(bounty_object_id))
        
        print(' last check: ', mongo.db.bounties.find_one({"_id": bounty_object_id}))
        bounty = mongo.db.bounties.find_one({"_id": bounty_object_id})
        #print('bounty title: ', bounty['bounty_title'] ,' bounty text: ', bounty["text"])

        if not bounty:
            print('no bounty found')
            return jsonify({"error": "Bounty not found"}), 404

        new_response = {
            "author_name": user['username'],
            "author_id": user['_id'],
            "text": response_text,
            "date": datetime.datetime.utcnow(),
            "bounty_title": bounty['title'],
            "bounty_id": bounty['_id'],
            "responses": []
        }
        print()
        print('new_response: ', new_response)
        print()
        mongo.db.bounties.update_one(
            {"_id": ObjectId(bounty_id)},
            {"$push": {"responses": new_response}}
        )

        return jsonify({"message": "Response added successfully", "new_response": convert_objectid_to_str(new_response)}), 200

    except Exception as e:
        return jsonify({"error": f"Error adding response: {e}"}), 500


