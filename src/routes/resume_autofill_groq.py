
from flask import Blueprint, request, jsonify
from flask import current_app as app
from flask_cors import cross_origin
from groq import Groq
import os
from dotenv import load_dotenv
import re
import json

resume_autifll_groq = Blueprint('resume_autifll_groq', __name__)

# Load environment variables from .env file
load_dotenv()

client = Groq(
    api_key=os.environ.get("GROQCLOUD_API_KEY"),
)

def summarize_resume_text(text):
    try:
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Please do not include headers like 'Summary:' when summarizing content."
                },
                {
                    "role": "user",
                    "content": f"For the following resume, please write a concise (less than 200 words) bio for this person in the first person, also provide lists for suggested interests, suggested skills, a string for their latest university, a string for major, and a string for graduation year. If there are projects on the resume, also include the title of the project and its description (make the description be as long as possible). Please always format your response as a json with keys: bio, skills, interests, latestUniversity, major, grad_yr, projects (with contents title and desc). This is very important: the entirety of your response should constitute a valid JSON. There should be no json tags in the front or any leading/trailing text. Only give the json. Here is the text:\n\n{text}"
                }
            ],
            model="llama3-70b-8192",
            max_tokens=1000,
            temperature=0.2
        )
        message_content = response.choices[0].message.content.strip()
        print(f'Here is the response: {message_content}')
        
        # Remove trailing commas from JSON string
        message_content = remove_trailing_commas(message_content)

        print()
        print()
        print(f"SUMMARIZE_RESUME_TEXT message_content {message_content}")
        print()
        print()
        # Validate and parse JSON format
        try:
            json_content = json.loads(message_content)
            print('here is json content: ', json_content)
        except json.JSONDecodeError as e:
            print(f"JSONDecodeError: {e}")
            return {}  # Return an empty dict if there's an error
        
        return json_content
    except Exception as e:
        print(f"Error summarizing text: {e}")
        return {}

def remove_trailing_commas(json_str):
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
    if json_str and json_str[-1] != '}':
        json_str += '}'
    return json_str


def validate_json(json_str):
    try:
        json.loads(json_str)
        return True
    except json.JSONDecodeError:
        return False

def validate_and_correct_json(json_str):
    try:
        json_obj = json.loads(json_str)
        return json.dumps(json_obj)
    except json.JSONDecodeError:
        return '{}'

def validate_and_regenerate_json(file_text):
    summary = summarize_resume_text(file_text)

    if not validate_json(json.dumps(summary)):
        print("Invalid JSON for summary, regenerating...")
        summary = summarize_resume_text(file_text)

    return summary



@resume_autifll_groq.route('/groqResumeParser', methods=['POST', 'OPTIONS'])
@cross_origin()
def resume_parser():
    print('Opened the resume parser route')
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'}), 200
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    try:
        file_text = extract_text_from_file(file)
        
        if not file_text:
            return jsonify({'error': 'Failed to extract text from the file or file is empty'}), 400

        summary = validate_and_regenerate_json(file_text)
        print(f'here is the summary: {summary}')
        return jsonify({'summary': summary}), 200
    except Exception as e:
        print(f"Error parsing resume: {e}")
        return jsonify({'error': str(e)}), 500
    



import os
import io
import PyPDF4
from pdfminer.high_level import extract_text as pdfminer_extract
import pytesseract
from pdf2image import convert_from_bytes
from docx import Document
from werkzeug.datastructures import FileStorage

def extract_text_from_file(file):
    """
    Extract text from PDF and DOCX files using multiple methods.
    
    :param file: A FileStorage object containing the document data
    :return: Extracted text as a string
    """
    if not isinstance(file, FileStorage):
        raise ValueError("Invalid file object")

    filename = file.filename
    file_extension = os.path.splitext(filename)[1].lower()

    try:
        if file_extension == '.pdf':
            return extract_text_from_pdf(file)
        elif file_extension == '.docx':
            return extract_text_from_docx(file)
        else:
            raise ValueError("Unsupported file type. Only .pdf and .docx are supported.")
    except Exception as e:
        print(f"Error extracting text from file: {e}")
        raise

def extract_text_from_pdf(pdf_file):
    """
    Extract text from a PDF file using multiple methods.
    """
    text = ""
    
    # Method 1: PyPDF4 (for PDFs with embedded text)
    try:
        pdf_file.seek(0)
        reader = PyPDF4.PdfFileReader(pdf_file)
        for page in range(reader.numPages):
            text += reader.getPage(page).extractText() or ""
        
        if text.strip():
            return text.strip()
    except Exception as e:
        print(f"PyPDF4 extraction failed: {e}")
    
    # Method 2: pdfminer (for more complex PDFs with embedded text)
    try:
        pdf_file.seek(0)
        text = pdfminer_extract(io.BytesIO(pdf_file.read()))
        
        if text.strip():
            return text.strip()
    except Exception as e:
        print(f"pdfminer extraction failed: {e}")
    
    # Method 3: OCR with Tesseract (for scanned PDFs or images)
    try:
        pdf_file.seek(0)
        images = convert_from_bytes(pdf_file.read())
        for image in images:
            text += pytesseract.image_to_string(image)
        
        if text.strip():
            return text.strip()
    except Exception as e:
        print(f"OCR extraction failed: {e}")
    
    raise ValueError("Text extraction failed for all PDF methods.")

def extract_text_from_docx(docx_file):
    """
    Extract text from a DOCX file.
    """
    try:
        doc = Document(docx_file)
        return '\n'.join([paragraph.text for paragraph in doc.paragraphs])
    except Exception as e:
        print(f"DOCX extraction failed: {e}")
        raise ValueError("Text extraction failed for DOCX file.")

