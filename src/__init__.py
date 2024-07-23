

import os
from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS
from flask_pymongo import PyMongo
from flask_jwt_extended import JWTManager
from flask_session import Session
from datetime import timedelta
import certifi
import ssl

load_dotenv()


mongo = PyMongo()
jwt = JWTManager()
sess = Session()

#seeing if commit works

def create_app():
    app = Flask(__name__)
    #CORS(app, supports_credentials=True, resources={r"/*": {"origins": "https://silomvp-040bbdc854fa.herokuapp.com"}})
    #CORS(app)
    CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True, expose_headers=["Authorization"])


    app.config['SECRET_KEY'] = 'your_secret_key'
    app.config["JWT_SECRET_KEY"] = 'your_jwt_secret_key'
    app.config['JWT_TOKEN_LOCATION'] = ['headers']
    app.config['MONGO_URI'] = os.getenv('MONGO_URI')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=1)
    app.config['SESSION_TYPE'] = 'filesystem'

    #@app.after_request
    #def after_request(response):
    #    #response.headers.add('Access-Control-Allow-')
    #    response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
    #    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    #    return response

    mongo.init_app(app)
    jwt.init_app(app)
    sess.init_app(app)

    from .routes import main_bp
    app.register_blueprint(main_bp)

    return app



