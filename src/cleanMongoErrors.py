## !!!
## DANGER DO NOT USE ON PRODUCTION UNTIL TESTED
## !!!

import pymongo
from bson import ObjectId
import bson.errors
import sys
import os 


def clean_projects():
    mongo_uri = os.getenv('MONGO_URI')
    try:
        # Connect to MongoDB
        client = pymongo.MongoClient(mongo_uri)
        db = client.get_default_database()  # or specify db name: client['your_database_name']

        print("Connected to MongoDB.")

        # Fetch all users' portfolios and aggregate project IDs
        print("Aggregating project IDs from user portfolios...")
        users = db.users.find({}, {"portfolio": 1})
        aggregated_project_ids = set()

        for user in users:
            portfolio = user.get('portfolio', [])
            if portfolio:
                for pid in portfolio:
                    if isinstance(pid, str):
                        if is_valid_objectid(pid):
                            pid = ObjectId(pid)  # Convert string to ObjectId if valid
                        else:
                            print(f"Invalid ObjectId format: {pid}")
                            continue
                    elif not isinstance(pid, ObjectId):
                        print(f"Unexpected type for project ID: {pid}. Skipping.")
                        continue
                    aggregated_project_ids.add(pid)

        print(f"Aggregated {len(aggregated_project_ids)} unique project IDs from user portfolios.")

        # Fetch all projects and remove those not in the aggregated set
        print("Removing projects not in aggregated portfolio project IDs...")
        existing_projects = db.projects.find({}, {"_id": 1})
        projects_removed = 0

        for project in existing_projects:
            project_id = project['_id']
            if project_id not in aggregated_project_ids:
                db.projects.delete_one({"_id": project_id})
                projects_removed += 1
                print(f"Removed project with ID: {project_id}")

        print(f"Removed {projects_removed} projects that were not referenced in any user portfolio.")

    except Exception as e:
        print(f"Error in clean_projects: {str(e)}")
        sys.exit(1)


def clean_user_portfolios():
    mongo_uri = os.getenv('MONGO_URI')
    try:
        # Connect to MongoDB
        client = pymongo.MongoClient(mongo_uri)
        db = client.get_default_database()  # or specify db name: client['your_database_name']

        print("Connected to MongoDB.")

        # Fetch all existing project IDs from the projects collection
        print("Fetching existing project IDs...")
        existing_projects = db.projects.find({}, {"_id": 1})
        existing_project_ids = set(project['_id'] for project in existing_projects)  # Use ObjectId directly
        print(f"Found {len(existing_project_ids)} existing projects.")

        # Fetch all users
        print("Fetching all users...")
        users = db.users.find()
        users_processed = 0
        portfolios_updated = 0

        for user in users:
            users_processed += 1
            user_id = user['_id']
            portfolio = user.get('portfolio', [])
            if not portfolio:
                continue  # Skip if the portfolio is empty

            # Normalize the portfolio array to ensure all elements are ObjectIds
            normalized_portfolio = []
            for pid in portfolio:
                if isinstance(pid, str):
                    if is_valid_objectid(pid):
                        pid = ObjectId(pid)  # Convert string to ObjectId if valid
                    else:
                        print(f"Invalid ObjectId format: {pid}")
                        continue
                elif not isinstance(pid, ObjectId):
                    print(f"Unexpected type for project ID: {pid}. Skipping.")
                    continue
                
                normalized_portfolio.append(pid)  # Add ObjectId (or already valid pid) to normalized portfolio

            cleaned_portfolio = [pid for pid in normalized_portfolio if pid in existing_project_ids]

            if cleaned_portfolio != normalized_portfolio:
                # Update the user's portfolio in the database
                db.users.update_one(
                    {"_id": user_id},
                    {"$set": {"portfolio": cleaned_portfolio}}
                )
                portfolios_updated += 1
                print(f"Updated portfolio for user {_id_str(user_id)}.")

        print(f"Processed {users_processed} users.")
        print(f"Updated {portfolios_updated} user portfolios.")
        print("User portfolios cleaned successfully.")

    except Exception as e:
        print(f"Error in clean_user_portfolios: {str(e)}")
        sys.exit(1)


def is_valid_objectid(value):
    try:
        ObjectId(value)
        return True
    except (bson.errors.InvalidId, TypeError):
        return False

def _id_str(obj_id):
    return str(obj_id) if isinstance(obj_id, ObjectId) else obj_id


if __name__ == "__main__":
    clean_user_portfolios()
    clean_projects()