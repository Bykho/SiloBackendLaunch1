


from pymongo import MongoClient
from werkzeug.security import generate_password_hash
import urllib.parse
import ssl
import uuid

# Encode the password and username
username = urllib.parse.quote_plus('nico')
password = urllib.parse.quote_plus('PleaseWork!')

# Initialize MongoClient
client = MongoClient(
    f"mongodb+srv://{username}:{password}@cluster0.iyzohjf.mongodb.net/trialDB?retryWrites=true&w=majority&appName=Cluster0",
    ssl = True,
    ssl_cert_reqs = ssl.CERT_NONE,
)

db = client["trialDB"]

class Project:
    def __init__(self, project_name, project_description='', project_link='', github_link='', 
                 media_link='', markdown_link='', project_id=None, impactful_upvotes=None, 
                 interesting_upvote=None, innovative_upvote=None, tags=None, comments=None):
        self.project_name = project_name
        self.project_description = project_description
        self.project_link = project_link
        self.github_link = github_link
        self.media_link = media_link
        self.markdown_link = markdown_link
        self.project_id = project_id or self.generate_project_id()
        self.impactful_upvotes = impactful_upvotes if impactful_upvotes is not None else []
        self.interesting_vote = interesting_upvote if interesting_upvote is not None else []
        self.innovative_upvote = innovative_upvote if innovative_upvote is not None else []
        self.tags = tags if tags is not None else []
        self.comments = comments if comments is not None else []

    def to_dict(self):
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "project_description": self.project_description,
            "project_link": self.project_link,
            "github_link": self.github_link,
            "media_link": self.media_link,
            "markdown_link": self.markdown_link,
            "impactful_upvotes": self.impactful_upvotes,
            "interesting_vote" : self.interesting_vote,
            "innovative_upvote": self.innovative_upvote,
            "topics": self.tags,
            "comments": self.comments,
        }
    
    @staticmethod
    def generate_project_id():
        return str(uuid.uuid4())



class User:
    def __init__(self, username, email, password, university, user_type, interests=None, skills=None, biography='',
                profile_photo='', personal_website='', papers=None, orgs=None, comments=None, portfolio=None,
                 impactful_upvoted_projects=None, interesting_upvotes_projects=None, innovative_upvotes_projects=None ):
        self.username = username
        self.email = email
        self.password = generate_password_hash(password)
        self.university = university
        self.user_type = user_type
        self.interests = interests if interests is not None else []
        self.skills = skills if skills is not None else []
        self.biography = biography
        self.profile_photo = profile_photo
        self.personal_website = personal_website
        self.papers = papers if papers is not None else []
        self.orgs = orgs if orgs is not None else []
        self.comments = comments if comments is not None else []
        self.portfolio = portfolio if portfolio is not None else []
        self.impactful_upvoted_projects = impactful_upvoted_projects if impactful_upvoted_projects is not None else []
        self.interesting_upvotes_projects = interesting_upvotes_projects if interesting_upvotes_projects is not None else []
        self.innovative_upvotes_projects = innovative_upvotes_projects if innovative_upvotes_projects is not None else []
        print(f"Initialized User: {self.username}, {self.email}, {self.university}, {self.user_type}, portfolio: {self.portfolio}")

    def add_project(self, project):
        if isinstance(project, Project):
            self.portfolio.append(project.to_dict())
        else:
            raise ValueError("Invalid project. Must be instance of project class.")

    def save(self):
        print("Attempting to save user:", self.username)
        try:
            result = db.users.insert_one({
                "username": self.username,
                "email": self.email,
                "password": self.password,
                "university": self.university,
                "user_type": self.user_type,
                "interests": self.interests,
                "skills": self.skills,
                "biography": self.biography,
                "profile_photo": self.profile_photo,
                "personal_website": self.personal_website,
                "papers": self.papers,
                "orgs": self.orgs,
                "comments": self.comments,
                "portfolio": self.portfolio,
                "impactful_upvoted_projects": self.impactful_upvoted_projects,
                "interesting_upvotes_projects": self.interesting_upvotes_projects,
                "innovative_upvotes_projects": self.innovative_upvotes_projects,
            })
            print("User saved successfully:", result.inserted_id)
        except Exception as e:
            print("Failed to save user:", str(e))
            raise

    @staticmethod
    def find(email):
        print("Searching for user by email:", email)
        user = db.users.find_one({"email": email})
        print("Found user:", user)
        return user

class Student(User):
    def __init__(self, username, email, password, university, user_type):
        super().__init__(username, email, password, university, user_type)
        print(f"Initialized Student: {self.username}")

    def save(self):
        print("Attempting to save student:", self.username)
        super().save()

class Faculty(User):
    def __init__(self, username, email, password, university, user_type, department=None, position=None):
        super().__init__(username, email, password, university, user_type)
        self.department = department
        self.position = position
        print(f"Initialized Faculty: {self.username}, Department: {self.department}, Position: {self.position}")

    def save(self):
        print("Attempting to save faculty:", self.username)
        try:
            result = db.users.insert_one({
                "username": self.username,
                "email": self.email,
                "password": self.password,
                "university": self.university,
                "user_type": self.user_type,
                "department": self.department,
                "position": self.position
            })
            print("Faculty saved successfully:", result.inserted_id)
        except Exception as e:
            print("Failed to save faculty:", str(e))
            raise