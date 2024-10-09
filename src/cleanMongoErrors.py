
## !!!
## DANGER DO NOT USE ON PRODUCTION UNTIL TESTED
## !!!

import pymongo
from bson import ObjectId
import sys
import os 


def clean_user_portfolios():
    mongo_uri = os.getenv('MONGO_URI')
    try:
        # Replace the connection URI with your MongoDB connection string
        client = pymongo.MongoClient(mongo_uri)
        db = client.get_default_database()  # or specify db name: client['your_database_name']

        print("Connected to MongoDB.")

        # Fetch all existing project IDs from the projects collection
        print("Fetching existing project IDs...")
        existing_projects = db.projects.find({}, {"_id": 1})
        existing_project_ids = set(str(project['_id']) for project in existing_projects)
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

            # Assuming portfolio contains project IDs as strings
            # If they are ObjectIds, adjust the code accordingly
            cleaned_portfolio = [pid for pid in portfolio if pid in existing_project_ids]

            if cleaned_portfolio != portfolio:
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

def _id_str(obj_id):
    return str(obj_id) if isinstance(obj_id, ObjectId) else obj_id

if __name__ == "__main__":
    clean_user_portfolios()

