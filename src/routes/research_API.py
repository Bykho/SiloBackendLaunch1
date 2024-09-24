from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
import requests
import xml.etree.ElementTree as ET
from bson import ObjectId
from flask_pymongo import PyMongo
from .. import mongo
from flask import current_app as app


research_bp = Blueprint('research', __name__)

def construct_arxiv_query(terms):
    """
    Construct a properly formatted query string for the arXiv API.
    """
    formatted_terms = [f'"{term}"' if ' ' in term else term for term in terms if term.strip()]
    return f"({' OR '.join(formatted_terms)})"

@research_bp.route('/query_arxiv', methods=['GET'])
@jwt_required()
def query_arxiv():
    print("gothere!!!")
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')

    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    skills = user.get('skills', [])
    interests = user.get('interests', [])
    search_terms = skills + interests
    
    user_profile = construct_arxiv_query(search_terms)
    print(user_profile, "userprofile")

    params = {
        'search_query': f'all:{user_profile}',
        'start': request.args.get('start', '0'),
        'max_results': request.args.get('max', '40'),
        'sortBy': request.args.get('sort', 'relevance'),
        'sortOrder': request.args.get('order', 'descending')
    }
    base_url = 'http://export.arxiv.org/api/query'
    
    try:
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        
        results = []
        for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
            title = entry.find('{http://www.w3.org/2005/Atom}title').text
            summary = entry.find('{http://www.w3.org/2005/Atom}summary').text
            authors = [author.find('{http://www.w3.org/2005/Atom}name').text 
                       for author in entry.findall('{http://www.w3.org/2005/Atom}author')]
            published = entry.find('{http://www.w3.org/2005/Atom}published').text
            link = entry.find('{http://www.w3.org/2005/Atom}id').text
            
            results.append({
                'title': title,
                'summary': summary,
                'authors': authors,
                'published': published,
                'link': link
            })

            print(results)
        
        return jsonify({
            'status': 'success',
            'data': results,
            'total_results': len(results),
            'search_params': params
        })
    
    except requests.RequestException as e:
        return jsonify({'status': 'error', 'message': f'Failed to fetch data from arXiv API: {str(e)}'}), 500
    except ET.ParseError:
        return jsonify({'status': 'error', 'message': 'Failed to parse XML response from arXiv API'}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'An unexpected error occurred: {str(e)}'}), 500


@research_bp.route('/save_paper', methods=['POST'])
@jwt_required()
def save_paper():
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')

    paper_data = request.json
    title = paper_data.get('title')
    url = paper_data.get('url')

    if not title or not url:
        return jsonify({'status': 'error', 'message': 'Missing title or URL'}), 400

    result = mongo.db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$addToSet": {"papers": {"title": title, "url": url}}}
    )

    if result.modified_count > 0:
        return jsonify({'status': 'success', 'message': 'Paper saved successfully'}), 200
    else:
        return jsonify({'status': 'error', 'message': 'Failed to save paper'}), 500


@research_bp.route('/unsave_paper', methods=['POST'])
@jwt_required()
def unsave_paper():
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')

    paper_data = request.json
    title = paper_data.get('title')
    url = paper_data.get('url')

    if not title or not url:
        return jsonify({'status': 'error', 'message': 'Missing title or URL'}), 400

    result = mongo.db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$pull": {"papers": {"title": title, "url": url}}}
    )

    if result.modified_count > 0:
        return jsonify({'status': 'success', 'message': 'Paper unsaved successfully'}), 200
    else:
        return jsonify({'status': 'error', 'message': 'Paper not found or failed to unsave'}), 200



@research_bp.route('/get_saved_papers', methods=['GET'])
@jwt_required()
def get_saved_papers():
    jwt_claims = get_jwt()
    user_id = jwt_claims.get('_id')

    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    saved_papers = user.get('papers', [])
    return jsonify({'status': 'success', 'data': saved_papers}), 200
