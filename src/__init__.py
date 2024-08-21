

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
from flask_mail import Mail


#print("MONGO_URI before load_dotenv:", os.getenv('MONGO_URI'))
load_dotenv()
#print("MONGO_URI after load_dotenv:", os.getenv('MONGO_URI'))

print("Current working directory:", os.getcwd())

mongo_uri = os.getenv('MONGO_URI')

if mongo_uri is None:
    print("MONGO_URI is not set correctly. Falling back to default.")
    mongo_uri = 'default_value_if_missing'

#print("MONGO_URI set to:", mongo_uri)

mongo = PyMongo()
jwt = JWTManager()
sess = Session()
mail = Mail()

#seeing if commit works

def create_app():
    app = Flask(__name__)
    #CORS(app, supports_credentials=True, resources={r"/*": {"origins": "https://silomvp-040bbdc854fa.herokuapp.com"}})
    #CORS(app)
    CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True, expose_headers=["Authorization"])


    app.config['SECRET_KEY'] = 'your_secret_key'
    app.config["JWT_SECRET_KEY"] = 'your_jwt_secret_key'
    app.config['JWT_TOKEN_LOCATION'] = ['headers']
    app.config['MONGO_URI'] = mongo_uri
    #print("Connecting to MongoDB URI:", app.config['MONGO_URI'])
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=1)
    app.config['SESSION_TYPE'] = 'filesystem'


    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
    app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT'))
    app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS') == 'True'
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')

    mail.init_app(app)
    mongo.init_app(app)
    jwt.init_app(app)
    sess.init_app(app)

    from .routes.comment_routes import comment_bp
    from .routes.feed_routes import feed_bp
    from .routes.group_routes import group_bp
    from .routes.project_routes import project_bp
    from .routes.user_routes import user_bp
    from .routes.utility_routes import utility_bp
    from .routes.autofiller_routes import autofiller_bp
    from .routes.code_autofill_groq import groq_code_autofill_bp
    from .routes.pdf_autofill_groq import pdf_autofill_groq
    from .routes.codeAutoHolder import codeAutoHolder
    from .routes.resume_autofill_groq import resume_autifll_groq
    from .routes.profile_scores_VS import VSscores_bp
    from .routes.resume_autofill_VS import VSresume_autofill_bp
    from .routes.code_autofill_VS import VS_code_autofill_bp

    app.register_blueprint(comment_bp)
    app.register_blueprint(feed_bp)
    app.register_blueprint(group_bp)
    app.register_blueprint(project_bp)    
    app.register_blueprint(user_bp)
    app.register_blueprint(utility_bp)
    app.register_blueprint(autofiller_bp)
    app.register_blueprint(groq_code_autofill_bp)
    app.register_blueprint(resume_autifll_groq)
    app.register_blueprint(pdf_autofill_groq)
    app.register_blueprint(codeAutoHolder)
    app.register_blueprint(VSscores_bp)
    app.register_blueprint(VSresume_autofill_bp)
    app.register_blueprint(VS_code_autofill_bp)


    return app

