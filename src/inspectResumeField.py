import os
import sys
import pymongo
from bson import ObjectId

def inspect_specific_user_resume(user_id_str):
    mongo_uri = "mongodb+srv://nico:PleaseWork!@cluster0.iyzohjf.mongodb.net/ProductionDatabase?retryWrites=true&w=majority&ssl=true&tlsAllowInvalidCertificates=true"
    try:
        # Connect to MongoDB
        client = pymongo.MongoClient(mongo_uri)
        db = client.get_default_database()  # or specify db name: client['your_database_name']

        print("Connected to MongoDB.")

        # Convert string to ObjectId
        user_id = ObjectId(user_id_str)

        # Fetch the specific user
        user = db.users.find_one({"_id": user_id})

        if user is None:
            print(f"No user found with ID: {user_id_str}")
            return

        username = user.get('username', 'Unknown')
        resume = user.get('resume')

        print(f"\nInspecting resume for user: {username} (ID: {user_id})")
        
        if resume is None:
            print("Resume field is missing.")
        elif isinstance(resume, dict) and not resume:
            print("Resume field is an empty object.")
        elif isinstance(resume, dict):
            print("Resume field is an object with the following keys:")
            for key, value in resume.items():
                print(f"  - {key}: {type(value)}")
                if isinstance(value, str):
                    print(f"    First 100 characters: {value[:100]}")
        elif isinstance(resume, str):
            if resume.strip():
                print(f"Resume field is a non-empty string of length {len(resume)}.")
                print("First 100 characters:", resume[:100])
            else:
                print("Resume field is an empty string.")
        else:
            print(f"Resume field has an unexpected type: {type(resume)}")

    except pymongo.errors.PyMongoError as e:
        print(f"MongoDB Error: {str(e)}")
    except Exception as e:
        print(f"Error in inspect_specific_user_resume: {str(e)}")
    finally:
        client.close()

if __name__ == "__main__":
    user_id_to_inspect = "66e1de66d9a4e041e968bef7"
    inspect_specific_user_resume(user_id_to_inspect)