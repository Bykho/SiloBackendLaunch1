import os
import openai
from github import Github
import base64
from tqdm import tqdm
from dotenv import load_dotenv
import time
from pinecone import Pinecone, ServerlessSpec
import re
from pymongo import MongoClient
import ast
from typing import List, Dict

# Load environment variables
load_dotenv()

# Retrieve GitHub Token
github_token = os.getenv('GITHUB_API_TOKEN')
if not github_token:
    raise ValueError("GITHUB_TOKEN not found in environment variables.")

print(f"GitHub Token loaded: {'***' + github_token[-4:]}")  # Masked for security

# Initialize GitHub client with the new token
g = Github(github_token)

# Initialize other clients
openai.api_key = os.getenv('OPENAI_API_KEY')
if not openai.api_key:
    raise ValueError("OPENAI_API_KEY not found in environment variables.")

# Initialize MongoDB
MONGO_URI = os.getenv('MONGO_URI')
if not MONGO_URI:
    raise ValueError("MONGO_URI not found in environment variables.")

mongo_client = MongoClient(MONGO_URI)
db = mongo_client['ProductionDatabase']
users_collection = db.users

# Initialize Pinecone
pinecone_api_key = os.getenv("PINECONE_KEY")
if not pinecone_api_key:
    raise ValueError("PINECONE_KEY not found in environment variables.")

pc = Pinecone(api_key=pinecone_api_key)

index_name = 'candidate-github-rag-test'
if index_name not in [index.name for index in pc.list_indexes()]:
    pc.create_index(
        name=index_name,
        dimension=1536,  # Adjust dimension as needed
        metric='cosine',
        spec=ServerlessSpec(cloud='gcp', region='us-west1')
    )

# Access the index
index = pc.Index(index_name)

print(f"Index {index_name} initialized.")

# Updated File filtering patterns
EXCLUDED_PATTERNS = [
    r'node_modules',
    r'virtualenvs?',
    r'venv\d*',
    r'env\d*',
    r'dist',
    r'build',
    r'target',
    r'bin',
    r'public',
    r'static',
    r'tests?',
    r'docs?',
    r'examples?',
    r'\.env$',
    r'\.prettierrc$',
    r'\.eslintrc$',
    r'tsconfig\.json$',
    r'package\.json$',
    r'yarn\.lock$',
    r'\.gitignore$',
    r'LICENSE$',
    r'CHANGELOG\.md$',
    r'CONTRIBUTING\.md$',
    r'\.DS_Store$',
    r'\.log$',
    r'\.min\.js$',
    r'\.(png|jpg|jpeg|gif|svg)$',
    r'\.(ttf|woff|woff2|eot)$',
    r'\.(json|yaml|yml|xml)$',
    r'pyvenv\.cfg$',   # Exclude pyvenv.cfg files
]

PRIORITIZED_EXTENSIONS = [
    '.js', '.ts', '.jsx', '.tsx', '.py', '.java',
    '.c', '.cpp', '.cs', '.rb', '.php', '.go', '.rs',
    '.md'  # Include markdown files (e.g., ReadMe)
]

def parse_python_functions(content: str, file_path: str) -> List[Dict]:
    """Parse Python file content into function-level chunks with context."""
    try:
        tree = ast.parse(content)
        functions = []

        # Track imports and global context
        imports = []
        global_vars = []

        for node in ast.walk(tree):
            # Collect imports
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(ast.unparse(node))

            # Collect global variables
            elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                global_vars.append(ast.unparse(node))

            # Process functions and classes
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                # Get the docstring if it exists
                docstring = ast.get_docstring(node)

                # Get function dependencies (other functions it calls)
                function_calls = []
                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                        function_calls.append(child.func.id)

                # Get the full source code
                function_code = ast.unparse(node)

                # Create context block
                context = "\n".join(imports + global_vars)

                functions.append({
                    'name': node.name,
                    'code': function_code,
                    'docstring': docstring,
                    'context': context,
                    'dependencies': list(set(function_calls)),
                    'file_path': file_path,
                    'type': 'class' if isinstance(node, ast.ClassDef) else 'function'
                })

        return functions
    except Exception as e:
        print(f"Error parsing Python file {file_path}: {e}")
        return []

def parse_javascript_functions(content: str, file_path: str) -> List[Dict]:
    """Parse JavaScript/TypeScript file content into function-level chunks."""
    functions = []

    # Patterns for different function types
    patterns = [
        # Regular functions
        r'(?:async\s+)?function\s+(\w+)\s*\([^)]*\)\s*{',
        # Arrow functions with explicit name
        r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>',
        # Class methods
        r'(?:async\s+)?(\w+)\s*\([^)]*\)\s*{',
        # Class declarations
        r'class\s+(\w+)\s*(?:extends\s+\w+\s*)?{'
    ]

    # Find all imports first
    import_pattern = r'^(?:import|export).*?;\s*$'
    imports = re.findall(import_pattern, content, re.MULTILINE)
    context = "\n".join(imports)

    # Find and process all functions
    for pattern in patterns:
        matches = re.finditer(pattern, content, re.MULTILINE)
        for match in matches:
            try:
                start = match.start()
                # Find the matching closing brace
                bracket_count = 0
                found_first = False
                end = start

                for i in range(start, len(content)):
                    if content[i] == '{':
                        bracket_count += 1
                        found_first = True
                    elif content[i] == '}':
                        bracket_count -= 1
                        if found_first and bracket_count == 0:
                            end = i + 1
                            break

                if end > start:
                    function_code = content[start:end]
                    function_name = match.group(1)

                    functions.append({
                        'name': function_name,
                        'code': function_code,
                        'context': context,
                        'file_path': file_path,
                        'dependencies': [],  # Could be enhanced with static analysis
                        'type': 'function'
                    })
            except Exception as e:
                print(f"Error processing function match in {file_path}: {e}")
                continue

    return functions

def group_related_functions(functions: List[Dict]) -> List[Dict]:
    """Group related functions based on dependencies and naming patterns."""
    grouped_functions = []
    processed = set()

    for func in functions:
        if func['name'] in processed:
            continue

        related_funcs = [func]
        processed.add(func['name'])

        # Group by class (for methods)
        if func['type'] == 'class':
            # Find all methods that might belong to this class
            for other_func in functions:
                if other_func['name'] in processed:
                    continue
                if func['file_path'] == other_func['file_path']:
                    related_funcs.append(other_func)
                    processed.add(other_func['name'])

        # Group by dependencies and naming patterns
        else:
            for other_func in functions:
                if other_func['name'] in processed:
                    continue

                # Check if functions are related
                if (func['name'] in other_func.get('dependencies', []) or
                    other_func['name'] in func.get('dependencies', []) or
                    similar_names(func['name'], other_func['name'])):
                    related_funcs.append(other_func)
                    processed.add(other_func['name'])

        # Combine related functions into a single chunk
        grouped_functions.append({
            'name': related_funcs[0]['name'],
            'code': '\n\n'.join(f['code'] for f in related_funcs),
            'context': related_funcs[0]['context'],
            'related_functions': [f['name'] for f in related_funcs],
            'file_path': func['file_path'],
            'type': func['type']
        })


    return grouped_functions

def similar_names(name1: str, name2: str) -> bool:
    """Check if function names are similar."""
    common_prefixes = ['get_', 'set_', 'update_', 'delete_', 'create_', 'fetch_', 'process_']
    common_suffixes = ['_async', '_sync', '_internal', '_helper', '_util', '_handler']

    # Remove common prefixes/suffixes
    for prefix in common_prefixes:
        if name1.startswith(prefix):
            name1 = name1[len(prefix):]
        if name2.startswith(prefix):
            name2 = name2[len(prefix):]

    for suffix in common_suffixes:
        if name1.endswith(suffix):
            name1 = name1[:-len(suffix)]
        if name2.endswith(suffix):
            name2 = name2[:-len(suffix)]

    # Check if the core names are similar
    return name1 == name2 or (
        len(name1) > 3 and len(name2) > 3 and
        (name1 in name2 or name2 in name1)
    )

def extract_github_username(github_link):
    """Extract GitHub username from a given GitHub URL or username string."""
    if not github_link:
        return None
    pattern = r'(?:https?://)?(?:www\.)?github\.com/([^/]+)/?'
    match = re.search(pattern, github_link)
    if match:
        return match.group(1)
    return github_link.strip('/')

def get_users_with_github():
    """Get hardcoded Bykho user data."""
    return [{
        '_id': 'bykho_test',
        'github_link': 'github.com/Bykho'
    }]
    """Get all users with GitHub profiles from MongoDB.
    try:
        users = users_collection.find({
            '$or': [
                {'github_link': {'$exists': True, '$ne': ''}},
                {'personal_website': {'$regex': 'github\\.com', '$options': 'i'}}
            ],
            'github_processed': {'$ne': True}  # Skip already processed users
        })
        return list(users)
    except Exception as e:
        print(f"Error fetching users from MongoDB: {e}")
        return []
    """
        
def should_process_file(file_path):
    """Determine if a file should be processed based on patterns."""
    for pattern in EXCLUDED_PATTERNS:
        if re.search(pattern, file_path, re.IGNORECASE):
            return False

    _, ext = os.path.splitext(file_path)
    return ext.lower() in PRIORITIZED_EXTENSIONS

def process_file_content(file_data: Dict, repo_name: str, username: str) -> List[Dict]:
    """Process a file and prepare its chunks for embedding."""
    extension = file_data['extension']
    content = file_data['content']
    file_path = file_data['path']

    # Handle README files differently
    if file_data.get('is_readme'):
        return [{
            'id': f"{username}_{repo_name}_{file_path}",
            'text': f"Repository: {repo_name}\nDocumentation Type: README\n\n{content}",
            'metadata': {
                'username': username,
                'repo_name': repo_name,
                'file_path': file_path,
                'type': 'readme'
            }
        }]

    # Process code files
    if extension == '.py':
        functions = parse_python_functions(content, file_path)
    elif extension in ['.js', '.jsx', '.ts', '.tsx']:
        functions = parse_javascript_functions(content, file_path)
    else:
        # For other supported file types, treat as whole file
        return [{
            'id': f"{username}_{repo_name}_{file_path}",
            'text': f"File: {file_path}\n\n{content}",
            'metadata': {
                'username': username,
                'repo_name': repo_name,
                'file_path': file_path,
                'type': 'code_file'
            }
        }]

    # Group related functions
    grouped_functions = group_related_functions(functions)

    # Prepare chunks for embedding
    chunks = []
    for func in grouped_functions:
        chunks.append({
            'id': f"{username}_{repo_name}_{file_path}_{func['name']}",
            'text': f"File: {file_path}\n{func['type'].title()}: {func['name']}\n\nContext:\n{func['context']}\n\nCode:\n{func['code']}",
            'metadata': {
                'username': username,
                'repo_name': repo_name,
                'file_path': file_path,
                'function_name': func['name'],
                'related_functions': func.get('related_functions', []),
                'type': 'function' if func['type'] == 'function' else 'class'
            }
        })

    return chunks

def get_repository_files(repo):
    """Get all relevant files from a repository, excluding virtual environments."""
    files_data = []

    def is_virtual_env(contents):
        """Check if the current directory is a virtual environment by looking for indicators."""
        for content in contents:
            if content.type == "file" and content.name in ['pyvenv.cfg', 'activate', 'activate.bat', 'activate.ps1']:
                return True
        return False

    def process_contents(contents, current_path=""):
        for content in contents:
            # Construct the full path for the current content
            full_path = os.path.join(current_path, content.path) if current_path else content.path

            if content.type == "dir":
                # Fetch the contents of the directory to check for virtual environment indicators
                try:
                    dir_contents = repo.get_contents(content.path)
                except Exception as e:
                    print(f"Error accessing directory {content.path}: {e}")
                    continue

                if is_virtual_env(dir_contents):
                    print(f"Skipping virtual environment directory: {content.path}")
                    continue  # Skip processing this directory

                # Check if the directory matches any excluded patterns
                if any(re.search(pattern, content.path, re.IGNORECASE) for pattern in EXCLUDED_PATTERNS):
                    print(f"Skipping excluded directory: {content.path}")
                    continue

                # Recursively process the contents of the directory
                process_contents(dir_contents, current_path=content.path)

            elif content.type == "file":
                if should_process_file(content.path):
                    try:
                        file_content = base64.b64decode(content.content).decode('utf-8')
                        is_readme = content.name.lower() == 'readme.md'

                        files_data.append({
                            'name': content.name,
                            'path': content.path,
                            'content': file_content,
                            'extension': os.path.splitext(content.name)[1].lower(),
                            'is_readme': is_readme
                        })
                    except Exception as e:
                        print(f"Error processing file {content.path}: {e}")

    try:
        contents = repo.get_contents("")
        process_contents(contents)
    except Exception as e:
        print(f"Error accessing repository contents: {e}")

    return files_data

def process_batch(chunks):
    """Process a batch of chunks for embedding."""
    success = False
    retry_count = 0
    max_retries = 5
    sleep_time = 60  # in seconds

    while not success and retry_count < max_retries:
        try:
            # Generate embeddings
            texts = [chunk['text'] for chunk in chunks]
            response = openai.Embedding.create(
                input=texts,
                model='text-embedding-ada-002'
            )
            embeddings = [record['embedding'] for record in response['data']]

            # Prepare vectors for Pinecone
            vectors = []
            for idx, embedding in enumerate(embeddings):
                vector = {
                    'id': chunks[idx]['id'],
                    'values': embedding,
                    'metadata': chunks[idx]['metadata']
                }
                vectors.append(vector)

            # Upsert to Pinecone
            index.upsert(vectors)
            success = True
            print(f"Successfully processed batch of {len(vectors)} chunks")

        except openai.error.RateLimitError as e:
            print(f'OpenAI RateLimitError: {e}')
            retry_count += 1
            # Extract retry-after time if available
            retry_after = e.headers.get('Retry-After')
            if retry_after:
                sleep_time = int(retry_after)
            else:
                sleep_time *= 2  # Exponential backoff
            print(f'Retrying after {sleep_time} seconds...')
            time.sleep(sleep_time)

        except openai.error.APIError as e:
            print(f'OpenAI APIError: {e}')
            retry_count += 1
            sleep_time *= 2
            print(f'Retrying after {sleep_time} seconds...')
            time.sleep(sleep_time)

        except Exception as e:
            print(f'Error in process_batch: {e}')
            retry_count += 1
            sleep_time *= 2
            print(f'Retrying after {sleep_time} seconds...')
            time.sleep(sleep_time)

    if not success:
        print('Failed to process batch after multiple retries.')

def process_user_github(user):
    """Process all GitHub repositories for a single user."""
    github_link = user.get('github_link', user.get('personal_website', ''))
    username = extract_github_username(github_link)
    user_id = str(user.get('_id'))

    if not username:
        print(f"Could not extract GitHub username for user {user_id}")
        return False

    print(f"Processing GitHub repositories for user {username}")

    try:
        github_user = g.get_user(username)
        repositories = github_user.get_repos()

        batch_chunks = []

        for repo in repositories:
            print(f"Processing repository: {repo.name}")
            check_rate_limit()  # Check rate limit before processing
            files = get_repository_files(repo)

            for file in files:
                chunks = process_file_content(file, repo.name, username)
                batch_chunks.extend(chunks)

                if len(batch_chunks) >= 100:  # Process in batches of 100
                    process_batch(batch_chunks)
                    batch_chunks.clear()
                    # Optional: Add a short delay to prevent rapid API calls
                    time.sleep(1)

        # Process remaining chunks
        if batch_chunks:
            process_batch(batch_chunks)

        # Mark user as processed in MongoDB
        users_collection.update_one(
            {'_id': user.get('_id')},
            {'$set': {'github_processed': True}}
        )

        return True

    except Exception as e:
        print(f"Error processing GitHub data for user {username}: {e}")
        return False

def check_rate_limit():
    """Check the current GitHub API rate limit."""
    try:
        rate_limit = g.get_rate_limit()
        core_limits = rate_limit.core
        print(f"GitHub API Rate Limit: {core_limits.remaining}/{core_limits.limit} remaining.")
        reset_timestamp = core_limits.reset.timestamp()
        reset_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(reset_timestamp))
        print(f"Rate limit resets at: {reset_time}")
        if core_limits.remaining < 100:  # Threshold for pausing
            sleep_seconds = max(reset_timestamp - time.time(), 0) + 10  # Adding buffer
            print(f"Approaching rate limit. Sleeping for {sleep_seconds} seconds...")
            time.sleep(sleep_seconds)
    except Exception as e:
        print(f"Error checking rate limit: {e}")

def main():
    print("Starting GitHub RAG preparation...")
    check_rate_limit()  # Monitor rate limits
    
    # Create single user entry for Bykho
    user = {
        '_id': 'bykho_test',
        'github_link': 'github.com/Bykho'
    }
    
    print("Processing GitHub repositories for Bykho...")
    success = process_user_github(user)
    
    if success:
        print("Successfully processed Bykho's GitHub data")
    else:
        print("Failed to process Bykho's GitHub data")

if __name__ == '__main__':
    main()
