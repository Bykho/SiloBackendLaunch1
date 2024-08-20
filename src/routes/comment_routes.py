

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from bson import ObjectId
from ..routes_schema_utility import get_user_details, convert_objectid_to_str, get_user_context_details, get_user_feed_details, get_portfolio_details, get_project_feed_details
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt
from .. import mongo
from mixpanel_utils import track_event

comment_bp = Blueprint('comment', __name__)

@comment_bp.route('/getCommentsByIds', methods=['POST'])
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

@comment_bp.route('/handleGroupComment', methods=['POST'])
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
    

@comment_bp.route('/handleComment/<username>', methods=['POST'])
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
        
        track_event(str(author['_id']), "commented", {"project_id": str(project_id), "action": "comment"})

        return jsonify({"project": project, "comments": comments}), 200

    except Exception as e:
        print(f"Error occurred: {str(e)}")  # Log the error to the console
        return jsonify({"error": "An error occurred while handling the comment", "details": str(e)}), 500
    




