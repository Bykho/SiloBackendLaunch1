from flask import Flask
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

@app.route("/")
def index():
    mongo_uri = os.getenv('MONGO_URI')
    return f"MONGO_URI: {mongo_uri}"

if __name__ == "__main__":
    app.run(debug=True)
