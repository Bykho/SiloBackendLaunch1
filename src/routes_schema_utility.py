



from bson import ObjectId

def convert_objectid_to_str(data):
    if isinstance(data, list):
        return [convert_objectid_to_str(item) for item in data]
    elif isinstance(data, dict):
        return {key: convert_objectid_to_str(value) for key, value in data.items()}
    elif isinstance(data, ObjectId):
        return str(data)
    else:
        return data

def get_user_details(user):
    def convert_objectid_to_str(data):
        if isinstance(data, list):
            return [convert_objectid_to_str(item) for item in data]
        elif isinstance(data, dict):
            return {key: convert_objectid_to_str(value) for key, value in data.items()}
        elif isinstance(data, ObjectId):
            return str(data)
        else:
            return data


    if not user:
        return None
    user_details = {
        "_id": str(user['_id']),
        "username": user.get('username', ''),
        "email": user.get('email', ''),
        "university": user.get('university', ''),
        "user_type": user.get('user_type', ''),
        "grad": user.get('grad', ''),
        "major": user.get('major', ''),
        "interests": user.get('interests', []),
        "skills": user.get('skills', []),
        "biography": user.get('biography', ''),
        "profile_photo": user.get('profile_photo', ''),
        "personal_website": user.get('personal_website', ''),
        "orgs": user.get('orgs', []),
        "comments": user.get('comments', []),
        "upvotes": user.get('upvotes', []),
        "portfolio": user.get('portfolio', []),
        "links": user.get('links', []),
        "github_link": user.get("github_link", ''),
        "resume": user.get('resume', ''),
        "groups": user.get('groups', [])
    }
    return convert_objectid_to_str(user_details)


def get_user_context_details(user):
    def convert_objectid_to_str(data):
        if isinstance(data, list):
            return [convert_objectid_to_str(item) for item in data]
        elif isinstance(data, dict):
            return {key: convert_objectid_to_str(value) for key, value in data.items()}
        elif isinstance(data, ObjectId):
            return str(data)
        else:
            return data
        
    if not user:
        return None
    user_details = {
        "_id": str(user['_id']),
        "username": user.get('username', ''),
        "university": user.get('university', ''),
        "user_type": user.get('user_type', ''),
        "upvotes": user.get('upvotes', []),
    }
    return convert_objectid_to_str(user_details)


def get_user_feed_details(user):
    def convert_objectid_to_str(data):
        if isinstance(data, list):
            return [convert_objectid_to_str(item) for item in data]
        elif isinstance(data, dict):
            return {key: convert_objectid_to_str(value) for key, value in data.items()}
        elif isinstance(data, ObjectId):
            return str(data)
        else:
            return data
        
    if not user:
        return None
    user_details = {
        "_id": str(user['_id']),
        "username": user.get('username', ''),
        "email": user.get('email', ''),
        "interests": user.get('interests', []),
        "orgs": user.get('orgs', []),
        "university": user.get('university', ''),
        "user_type": user.get('user_type', ''),
        "portfolio": user.get('portfolio', ''),
    }
    return convert_objectid_to_str(user_details)

def get_portfolio_details(user):
    if not user:
        return None
    else:
        projects = [project for index, project in enumerate(user.get('portfolio', []))]
        return projects

def get_project_details(project):
    if not project:
        return None
    return {
        "_id": str(project.get('_id', '')),
        "comments": project.get('comments', []),
        "created_by": project.get('createdBy', ''),
        "upvotes": project.get('upvotes', []),
        "projectDescription": project.get('projectDescription', ''),
        "projectName": project.get('projectName', ''),
        "tags": project.get('tags', []),
    }


def get_project_feed_details(project):
    def convert_objectid_to_str(project):
        if isinstance(project, list):
            return [convert_objectid_to_str(item) for item in project]
        elif isinstance(project, dict):
            return {key: convert_objectid_to_str(value) for key, value in project.items()}
        elif isinstance(project, ObjectId):
            return str(project)
        else:
            return project
        
    if not project:
        return None
    return {
        "_id": str(project.get('_id', '')),
        "createdBy": project.get('createdBy', ''),
        "upvotes": project.get('upvotes', []),
        "projectDescription": project.get('projectDescription', ''),
        "projectName": project.get('projectName', ''),
        "tags": project.get('tags', []),
    }