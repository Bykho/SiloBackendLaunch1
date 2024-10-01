from flask import Blueprint, render_template
from flask import Blueprint, request, jsonify, send_from_directory
from flask import current_app as app
from flask_jwt_extended import jwt_required, get_jwt
import requests
from dotenv import load_dotenv
import os
import resend

load_dotenv()
resend.api_key = os.getenv("RESEND_KEY")

resend_bp = Blueprint('resend', __name__)

@resend_bp.route('/send_email')
def send_email(to_email):
    # Example data - in a real application, you'd get this from your database or user input
    email_data = {
        'edition': '1',
        'summary': 'This week in tech...',
        'articles': [
            {
                'date': 'October 1, 2024',
                'title': 'Article 1',
                'description': 'Description 1',
                'link': 'https://example.com/article1'
            },
            {
                'date': 'October 2, 2024',
                'title': 'Article 2',
                'description': 'Description 2',
                'link': 'https://example.com/article2'
            },
            {
                'date': 'October 3, 2024',
                'title': 'Article 3',
                'description': 'Description 3',
                'link': 'https://example.com/article3'
            },
            {
                'date': 'October 4, 2024',
                'title': 'Article 4',
                'description': 'Description 4',
                'link': 'https://example.com/article4'
            }
        ]
    }

    # Render the HTML template with the data
    html_content = render_template('email_template.html', **email_data)

    # Send the email
    r = resend.Emails.send({
        "from": "dan@silorepo.com",
        "to": to_email,
        "subject": "Your Week in Tech - Edition #{}".format(email_data['edition']),
        "html": html_content
    })

    return "Email sent successfully!"

@resend_bp.route('/add_contact', methods=['POST'])
def add_contact():
    email = request.json.get('email')
    if not email:
        return jsonify({"error": "Email is required"}), 400

    try:
        response = resend.Contacts.create({
            "email": email,
            "audience_id": "your_audience_id_here"  # Replace with your actual audience ID
        })
        return jsonify({"message": "Contact added successfully", "id": response.id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@resend_bp.route('/remove_contact', methods=['DELETE'])
def remove_contact():
    email = request.json.get('email')
    if not email:
        return jsonify({"error": "Email is required"}), 400

    try:
        resend.Contacts.remove(email)
        return jsonify({"message": "Contact removed successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
if __name__ == '__main__':
    app.run(debug=True)