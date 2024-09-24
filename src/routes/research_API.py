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
    # Remove any empty terms and wrap multi-word terms in quotes
    formatted_terms = [f'"{term}"' if ' ' in term else term for term in terms if term.strip()]
    
    # Join terms with OR, surrounded by parentheses
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

    # Combine skills and interests
    skills = user.get('skills', [])
    interests = user.get('interests', [])
    search_terms = skills + interests
    
    # Construct the arXiv query
    user_profile = construct_arxiv_query(search_terms)
    print(user_profile, "userprofile")

    # Search parameters
    params = {
        'search_query': f'all:{user_profile}',  # Search in all fields
        'start': request.args.get('start', '0'),
        'max_results': request.args.get('max', '20'),
        'sortBy': request.args.get('sort', 'relevance'),
        'sortOrder': request.args.get('order', 'descending')
    }

    # Construct the API URL
    base_url = 'http://export.arxiv.org/api/query'
    
    try:
        # Make the request to arXiv API
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()  # Raises an HTTPError for bad responses
        
        # Parse the XML response
        root = ET.fromstring(response.content)
        
        # Extract and format the results
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