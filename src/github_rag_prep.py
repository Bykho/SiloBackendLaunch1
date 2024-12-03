import os
import json
from github import Github, RateLimitExceededException, UnknownObjectException
from dotenv import load_dotenv
import openai
from rich.console import Console
from datetime import datetime
import re
from typing import List, Dict
import time
import tempfile
from tqdm import tqdm  # For progress bars
import pymongo
from bson import ObjectId
import bson.errors

# Define exclusion patterns
EXCLUDED_PATTERNS = [
    r'node_modules', r'virtualenvs?', r'venv\d*', r'env\d*', r'dist',
    r'build', r'target', r'bin', r'public', r'static', r'tests?',
    r'docs?', r'examples?', r'\.env$', r'\.prettierrc$', r'\.eslintrc$',
    r'tsconfig\.json$', r'package\.json$', r'yarn\.lock$', r'\.gitignore$',
    r'LICENSE$', r'CHANGELOG\.md$', r'CONTRIBUTING\.md$', r'\.DS_Store$',
    r'\.log$', r'\.min\.js$'
]

PRIORITIZED_EXTENSIONS = [
    '.js', '.ts', '.py', '.java', '.cpp', '.c', 
    '.php', '.rb', '.css', '.html', '.md', '.txt',
    '.json', '.xml'  # Only include extensions that OpenAI supports
]


# List of binary file extensions to skip
BINARY_EXTENSIONS = [
    '.pdf', '.docx', '.pptx', '.jpg', '.jpeg', '.png', '.gif',
    '.bmp', '.tiff', '.mp4', '.mp3', '.avi', '.mov', '.zip',
    '.tar', '.gz', '.7z', '.exe', '.dll'
]

# Mapping of repositories to specific branches
REPO_BRANCH_MAPPING = {
    "Bykho/SiloBackendLaunch1": "Development"
}

def load_environment():
    """Load environment variables and set API keys."""
    load_dotenv()
    openai_api_key = os.getenv('OPENAI_API_KEY')
    github_token = os.getenv('GITHUB_API_TOKEN')
    mongo_uri = os.getenv('MONGO_URI')
    
    if not all([openai_api_key, github_token, mongo_uri]):
        missing = []
        if not openai_api_key: missing.append("OPENAI_API_KEY")
        if not github_token: missing.append("GITHUB_API_TOKEN")
        if not mongo_uri: missing.append("MONGO_URI")
        raise ValueError(f"Missing environment variables: {', '.join(missing)}")
    
    openai.api_key = openai_api_key
    return github_token, mongo_uri

def is_virtual_env(contents):
    """Check if directory is a virtual environment."""
    for content in contents:
        if content.type == "file" and content.name in ['pyvenv.cfg', 'activate', 'activate.bat', 'activate.ps1']:
            return True
    return False

def should_process_file(file_path):
    """Determine if a file should be processed based on patterns."""
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    
    # Skip binary files
    if ext in BINARY_EXTENSIONS:
        return False
    
    # Handle special cases for TypeScript/JavaScript files
    if ext in ['.tsx', '.jsx']:
        return True  # We'll convert these to .ts or .js later
        
    # Include only prioritized extensions
    return ext in PRIORITIZED_EXTENSIONS

def get_repository_files(repo, user_id, github_username, repo_name, console, github_client, branch='main'):
    """Get all relevant files from a repository, excluding virtual environments and binary files."""
    files_data = []

    def process_contents(contents, current_path=""):
        for content in contents:
            full_path = os.path.join(current_path, content.path) if current_path else content.path

            if content.type == "dir":
                try:
                    dir_contents = repo.get_contents(content.path, ref=branch)
                    if is_virtual_env(dir_contents):
                        console.print(f"[yellow]Skipping virtual environment directory: {content.path}[/yellow]")
                        continue
                    if any(re.search(pattern, content.path, re.IGNORECASE) for pattern in EXCLUDED_PATTERNS):
                        console.print(f"[yellow]Skipping excluded directory: {content.path}[/yellow]")
                        continue
                    process_contents(dir_contents, current_path=content.path)
                except RateLimitExceededException:
                    reset_time = github_client.rate_limiting_resettime
                    sleep_time = reset_time - time.time() + 5  # Adding buffer
                    if sleep_time > 0:
                        console.print(f"[red]GitHub API rate limit exceeded. Sleeping for {int(sleep_time)} seconds...[/red]")
                        time.sleep(sleep_time)
                    # Retry after sleeping
                    try:
                        dir_contents = repo.get_contents(content.path, ref=branch)
                        process_contents(dir_contents, current_path=content.path)
                    except Exception as e:
                        console.print(f"[red]Error accessing directory {content.path} after rate limit reset: {e}[/red]")
                        continue
                except UnknownObjectException:
                    console.print(f"[red]Directory {content.path} not found. It might have been removed or is inaccessible.[/red]")
                    continue
                except Exception as e:
                    console.print(f"[red]Error accessing directory {content.path}: {e}[/red]")
                    continue

            elif content.type == "file" and should_process_file(content.path):
                try:
                    file_content = content.decoded_content.decode('utf-8')
                    if not file_content.strip():
                        console.print(f"[yellow]Skipping empty file: {content.path}[/yellow]")
                        continue
                    # Encode metadata into file_path with user_id
                    encoded_path = f"{user_id}_{github_username}/{repo_name}/{content.path}"
                    files_data.append({
                        'name': content.name,
                        'path': encoded_path,
                        'content': file_content,
                        'url': content.html_url
                    })
                    console.print(f"[green]Processed file: {encoded_path}[/green]")
                except Exception as e:
                    console.print(f"[red]Error processing file {content.path}: {e}[/red]")

    try:
        contents = repo.get_contents("", ref=branch)
        process_contents(contents)
    except RateLimitExceededException:
        reset_time = github_client.rate_limiting_resettime
        sleep_time = reset_time - time.time() + 5  # Adding buffer
        if sleep_time > 0:
            console.print(f"[red]GitHub API rate limit exceeded. Sleeping for {int(sleep_time)} seconds...[/red]")
            time.sleep(sleep_time)
        try:
            contents = repo.get_contents("", ref=branch)
            process_contents(contents)
        except Exception as e:
            console.print(f"[red]Error accessing repository contents after rate limit reset: {e}[/red]")

    except UnknownObjectException:
        console.print(f"[red]Repository {repo.full_name} not found.[/red]")
    except Exception as e:
        console.print(f"[red]Error accessing repository contents: {e}[/red]")

    return files_data

def save_vector_store_info(vector_stores_info):
    """Save vector store information to a JSON file."""
    output_dir = "vector_stores"
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(output_dir, f"vector_stores_{timestamp}.json")
    
    with open(filename, 'w') as f:
        json.dump(vector_stores_info, f, indent=2)
    
    return filename

def create_assistant(console):
    """Create a new Assistant with File Search enabled using a supported model."""
    try:
        assistant = openai.beta.assistants.create(
            name="GitHub Code Assistant",
            instructions="You are an assistant that can answer questions based on GitHub repository files.",
            model="gpt-4-turbo-preview",  # Use a supported model
            tools=[{"type": "file_search"}],
        )
        console.print(f"[green]Created new assistant: {assistant.id}[/green]")
        return assistant
    except Exception as e:
        console.print(f"[red]Error creating assistant: {e}[/red]")
        raise e



def setup_openai_vector_store(assistant_id, vector_store_id, files_data: List[Dict], console: Console, batch_size: int = 450):
    """Populate an existing OpenAI vector store with repository files in batches."""
    try:
        # Extension mapping for unsupported extensions
        extension_mapping = {
            '.tsx': '.ts',
            '.jsx': '.js'
        }
        
        # Process all files in batches
        total_files = len(files_data)
        batch_count = (total_files + batch_size - 1) // batch_size  # Calculate number of batches
        all_file_counts = {
            'cancelled': 0,
            'completed': 0,
            'failed': 0,
            'in_progress': 0,
            'total': 0
        }
        
        console.print(f"[blue]Processing {total_files} files in {batch_count} batches[/blue]")
        
        for batch_num in range(batch_count):
            start_idx = batch_num * batch_size
            end_idx = min((batch_num + 1) * batch_size, total_files)
            current_batch = files_data[start_idx:end_idx]
            
            console.print(f"\n[blue]Processing batch {batch_num + 1}/{batch_count} ({len(current_batch)} files)[/blue]")
            
            # Create a new temporary directory for this batch
            temp_dir = tempfile.mkdtemp()
            file_streams = []
            
            try:
                # Process files in current batch
                for file in current_batch:
                    # Extract the original extension in lowercase
                    _, ext = os.path.splitext(file['name'])
                    ext = ext.lower()

                    # Map unsupported extensions to supported ones
                    if ext in extension_mapping:
                        ext = extension_mapping[ext]

                    # Skip if extension is not supported by OpenAI
                    if ext not in PRIORITIZED_EXTENSIONS:
                        console.print(f"[yellow]Skipping file with unsupported extension: {file['name']}[/yellow]")
                        continue

                    # Ensure the encoded name ends with the correct extension
                    encoded_name = file['path'].replace("/", "_")
                    if not encoded_name.endswith(ext):
                        encoded_name = encoded_name.rsplit('.', 1)[0] + ext

                    temp_path = os.path.join(temp_dir, encoded_name)

                    try:
                        # Write content to a temp file
                        with open(temp_path, 'w', encoding='utf-8') as temp_file:
                            temp_file.write(file['content'])

                        # Open the renamed file for reading
                        file_streams.append(open(temp_path, "rb"))
                        console.print(f"[green]Prepared file: {encoded_name}[/green]")
                    except Exception as e:
                        console.print(f"[red]Error preparing file {encoded_name}: {e}[/red]")
                        continue

                if not file_streams:
                    console.print("[yellow]No valid files to upload in this batch[/yellow]")
                    continue

                # Upload current batch
                try:
                    file_batch = openai.beta.vector_stores.file_batches.upload_and_poll(
                        vector_store_id=vector_store_id,
                        files=file_streams
                    )
                    
                    # Update total counts
                    all_file_counts['cancelled'] += file_batch.file_counts.cancelled
                    all_file_counts['completed'] += file_batch.file_counts.completed
                    all_file_counts['failed'] += file_batch.file_counts.failed
                    all_file_counts['in_progress'] += file_batch.file_counts.in_progress
                    all_file_counts['total'] += file_batch.file_counts.total
                    
                    console.print(f"[green]Batch {batch_num + 1} upload complete: {file_batch.file_counts.completed} files processed[/green]")
                
                except Exception as e:
                    console.print(f"[red]Error uploading batch {batch_num + 1}: {e}[/red]")
                    continue
                
            finally:
                # Clean up the current batch's resources
                for f in file_streams:
                    try:
                        path = f.name
                        f.close()
                        os.remove(path)
                    except Exception as e:
                        console.print(f"[yellow]Error cleaning up file {f.name}: {e}[/yellow]")
                
                try:
                    os.rmdir(temp_dir)
                except Exception as e:
                    console.print(f"[yellow]Error removing temp directory: {e}[/yellow]")

        # After all batches are processed, attach vector store to assistant
        if all_file_counts['completed'] > 0:
            openai.beta.assistants.update(
                assistant_id=assistant_id,
                tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}}
            )
            console.print(f"[green]Attached vector store {vector_store_id} to assistant[/green]")
            
            return {
                'vector_store_id': vector_store_id,
                'file_count': all_file_counts
            }
        else:
            console.print("[red]No files were successfully uploaded[/red]")
            return None
    
    except Exception as e:
        console.print(f"[red]Error setting up vector store: {e}[/red]")
        return None




def is_valid_objectid(value):
    """Check if the provided value is a valid ObjectId."""
    try:
        ObjectId(value)
        return True
    except (bson.errors.InvalidId, TypeError):
        return False


def main():
    console = Console()
    console.print("[bold blue]Starting GitHub Repository Processing...[/bold blue]")
    temp_dir = None

    try:
        github_token, mongo_uri = load_environment()
        
        # Connect to MongoDB using pymongo
        client = pymongo.MongoClient(mongo_uri)
        db = client.get_default_database()
        console.print("[green]Connected to MongoDB.[/green]")

        github_client = Github(github_token)
        console.print("[green]Initialized GitHub client.[/green]")

        # Use existing Assistant ID
        assistant_id = "asst_hUjlVpcx3CKjAlvmFOgjjsbf"

        total_files = 0
        processed_repos = []
        all_files_data = []

        # Flag to break after the first successful upload
        first_upload_done = False

        try:
            # Fetch users with GitHub links
            users = db.users.find({
                "$or": [
                    {"github_link": {"$exists": True, "$ne": ""}},
                    {"personal_website": {"$regex": "github.com", "$options": "i"}}
                ]
            })

            # Process each user's repositories
            for user in users:
                if first_upload_done:  # Check the flag to break the loop
                    break

                try:
                    # Extract user information
                    user_id = str(user['_id'])
                    github_link = user.get('github_link', '')
                    personal_website = user.get('personal_website', '')
                    
                    # Get GitHub username
                    if github_link:
                        github_username = github_link.rstrip('/').split('/')[-1]
                    elif 'github.com' in personal_website.lower():
                        github_username = personal_website.rstrip('/').split('/')[-1]
                    else:
                        console.print(f"[yellow]No valid GitHub link found for user with ID '{user_id}'.[/yellow]")
                        continue
                    
                    # Process user's repositories
                    try:
                        user_data = github_client.get_user(github_username)
                        repositories = []
                        
                        # Fetch repositories with rate limit handling
                        try:
                            for repo in user_data.get_repos():
                                repositories.append(repo.full_name)
                        except RateLimitExceededException:
                            reset_time = github_client.rate_limiting_resettime
                            sleep_time = reset_time - time.time() + 5
                            if sleep_time > 0:
                                console.print(f"[red]GitHub API rate limit exceeded. Sleeping for {int(sleep_time)} seconds...[/red]")
                                time.sleep(sleep_time)
                                # Retry after sleep
                                for repo in user_data.get_repos():
                                    repositories.append(repo.full_name)
                        
                        if not repositories:
                            console.print(f"[yellow]No repositories found for user '{github_username}'.[/yellow]")
                            continue

                        console.print(f"[green]Found {len(repositories)} repositories for user '{github_username}'.[/green]")
                        
                        # Process each repository
                        for repo_path in repositories:
                            try:
                                owner, repo_name = repo_path.split('/')
                                branch = REPO_BRANCH_MAPPING.get(repo_path, 'main')
                                
                                repo = github_client.get_repo(repo_path)
                                files_data = get_repository_files(repo, user_id, github_username, repo_name, console, github_client, branch=branch)
                                
                                if files_data:
                                    all_files_data.extend(files_data)
                                    processed_repos.append(f"{owner}/{repo_name}")
                                    total_files += len(files_data)
                                    console.print(f"[green]Collected {len(files_data)} files from {owner}/{repo_name}[/green]")
                                
                                time.sleep(0.1)  # Rate limit protection
                                
                            except Exception as repo_error:
                                console.print(f"[red]Error processing repository {repo_path}: {repo_error}[/red]")
                                continue
                                
                    except UnknownObjectException:
                        console.print(f"[red]GitHub user '{github_username}' not found.[/red]")
                        continue
                    except Exception as user_error:
                        console.print(f"[red]Error processing user {github_username}: {user_error}[/red]")
                        continue
                        
                except Exception as user_processing_error:
                    console.print(f"[red]Error processing user data: {user_processing_error}[/red]")
                    continue

            # Upload to vector store if we have files
            if all_files_data:
                vector_store_id = "vs_uOiITYpmod1DxYVABOVaC8Xj"
                
                vector_store_info = setup_openai_vector_store(
                    assistant_id=assistant_id,
                    vector_store_id=vector_store_id,
                    files_data=all_files_data,
                    console=console
                )
                
                if vector_store_info:
                    # Save successful upload info
                    vector_store_info_saved = {
                        'assistant_id': assistant_id,
                        'vector_store_id': vector_store_info['vector_store_id'],
                        'file_count': vector_store_info['file_count'],
                        'repositories': processed_repos
                    }
                    
                    output_file = save_vector_store_info([vector_store_info_saved])
                    console.print(f"\n[green]Info saved to: {output_file}[/green]")
                    console.print(f"[green]Total completed uploads: {vector_store_info['file_count']['completed']}[/green]")
                    
                    if vector_store_info['file_count']['failed'] > 0:
                        console.print(f"[red]{vector_store_info['file_count']['failed']} files failed to upload.[/red]")
                    
                    console.print(f"[green]Repositories processed: {', '.join(processed_repos)}[/green]")
                    
                    # Set the flag to indicate the first upload is done
                    first_upload_done = True
                else:
                    console.print("[red]Failed to set up vector store.[/red]")
            else:
                console.print("[yellow]No files collected to upload.[/yellow]")

        finally:
            # Close MongoDB connection
            client.close()
            console.print("[green]Closed MongoDB connection.[/green]")

    except Exception as e:
        console.print(f"[red]Critical error in main process: {e}[/red]")
    finally:
        # Ensure any remaining temporary files are cleaned up
        if 'temp_dir' in locals() and temp_dir:
            try:
                import shutil
                shutil.rmtree(temp_dir)
                console.print("[green]Cleaned up temporary files.[/green]")
            except Exception as cleanup_error:
                console.print(f"[yellow]Error cleaning up temporary files: {cleanup_error}[/yellow]")

if __name__ == '__main__':
    main()


