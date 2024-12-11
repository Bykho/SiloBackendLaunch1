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
import pymongo
from bson import ObjectId
import bson.errors
from typing import List, Dict, Tuple

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
    '.json', '.xml', '.cs', '.tsx', '.jsx'
]

REPO_BRANCH_MAPPING = {
    "Bykho/SiloBackendLaunch1": "Development"
}

MAX_RETRIES = 40
BATCH_SIZE = 50  # Batch size for uploads

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
    return ext.lower() in PRIORITIZED_EXTENSIONS

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
                    sleep_time = reset_time - time.time() + 5
                    if sleep_time > 0:
                        console.print(f"[red]GitHub API rate limit exceeded. Sleeping for {int(sleep_time)} seconds...[/red]")
                        time.sleep(sleep_time)
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
        sleep_time = reset_time - time.time() + 5
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

def save_failed_uploads(failed_files, console):
    """Save failed upload details to a separate JSON file."""
    if not failed_files:
        console.print("[yellow]No failed uploads to save.[/yellow]")
        return
    
    try:
        output_dir = "failed_uploads"
        os.makedirs(output_dir, exist_ok=True)
        console.print(f"[green]Created or verified existence of directory: {output_dir}[/green]")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(output_dir, f"failed_uploads_{timestamp}.json")
        
        with open(filename, 'w') as f:
            json.dump(failed_files, f, indent=2)
        
        console.print(f"\n[yellow]Failed uploads details saved to: {os.path.abspath(filename)}[/yellow]")
    except Exception as e:
        console.print(f"[red]Failed to save failed uploads: {e}[/red]")

def create_assistant(console):
    """Create a new Assistant with File Search enabled using a supported model."""
    try:
        assistant = openai.beta.assistants.create(
            name="GitHub Code Assistant",
            instructions="You are an assistant that can answer questions based on GitHub repository files.",
            model="gpt-4-turbo-preview",
            tools=[{"type": "file_search"}],
        )
        console.print(f"[green]Created new assistant: {assistant.id}[/green]")
        return assistant
    except Exception as e:
        console.print(f"[red]Error creating assistant: {e}[/red]")
        raise e

def create_user_vector_store(console, github_username, github_url, user_id, db):
    """
    Create a new vector store for the user if it doesn't already exist.
    Returns the vector store ID if successful, None if failed.
    """
    try:
        # Check if user already has a vector store
        existing_store = db.vector_stores.find_one({"user_id": user_id})
        if existing_store:
            console.print(f"[yellow]Found existing vector store for user {github_username}: {existing_store['vectorstore_idx']}[/yellow]")
            return existing_store['vectorstore_idx']

        # Create new vector store using OpenAI API
        # : Replace the following line with the actual OpenAI API call to create a vector store
        # The current method is a placeholder and may not reflect the actual API
        vector_store = openai.beta.vector_stores.create(
            name=f"{github_username}_store",
            metadata={
                "user_id": user_id,
                "github_username": github_username,
                "github_url": github_url
            }
        )
        
        vectorstore_idx = vector_store.id  # Adjust based on actual API response
        
        # Insert record into vector_stores collection
        db.vector_stores.insert_one({
            "user_id": user_id,
            "username": github_username,
            "github_url": github_url,
            "vectorstore_idx": vectorstore_idx,
            "created_at": datetime.utcnow(),
            "status": "active",
            "file_counts": {
                "completed": 0,
                "failed": 0,
                "total": 0
            }
        })
        
        console.print(f"[green]Created new vector store for user {github_username}: {vectorstore_idx}[/green]")
        return vectorstore_idx
    
    except Exception as e:
        console.print(f"[red]Error creating vector store for user {github_username}: {e}[/red]")
        return None


def upload_files_to_vector_store(vector_store_id: str, files_data: List[Dict], console: Console, batch_size: int = 50):
    """
    Upload files to a vector store using the batch API.
    Returns a tuple of (success_count, failed_files).
    """
    try:
        temp_dir = tempfile.mkdtemp()
        temp_files = []
        file_ids = []
        failed_files = []
        current_batch = []
        
        # First, create all files and collect their IDs
        for file in files_data:
            try:
                # Create a temporary file
                file_name = file['name']
                temp_path = os.path.join(temp_dir, file_name)
                os.makedirs(os.path.dirname(temp_path), exist_ok=True)
                
                with open(temp_path, 'w', encoding='utf-8') as f:
                    f.write(file['content'])
                
                # Create file in OpenAI
                with open(temp_path, 'rb') as f:
                    openai_file = openai.files.create(
                        file=f,
                        purpose="assistants"
                    )
                
                current_batch.append({
                    'file_id': openai_file.id,
                    'name': file_name
                })
                temp_files.append(temp_path)
                
                # If we've reached batch size, process the batch
                if len(current_batch) >= batch_size:
                    success, failed = process_batch(vector_store_id, current_batch, console)
                    file_ids.extend(success)
                    failed_files.extend(failed)
                    current_batch = []
                
            except Exception as e:
                console.print(f"[red]Error processing file {file['name']}: {e}[/red]")
                failed_files.append({
                    'name': file['name'],
                    'error': str(e)
                })
        
        # Process any remaining files in the last batch
        if current_batch:
            success, failed = process_batch(vector_store_id, current_batch, console)
            file_ids.extend(success)
            failed_files.extend(failed)
        
        return len(file_ids), failed_files
            
    finally:
        # Cleanup temporary files
        for temp_file in temp_files:
            try:
                os.remove(temp_file)
            except Exception as e:
                console.print(f"[yellow]Failed to remove temp file {temp_file}: {e}[/yellow]")
        try:
            os.rmdir(temp_dir)
        except Exception as e:
            console.print(f"[yellow]Failed to remove temp directory: {e}[/yellow]")

def process_batch(vector_store_id: str, batch: List[Dict], console: Console) -> Tuple[List[str], List[Dict]]:
    """
    Process a batch of files using the vector store batch API.
    Returns (successful_file_ids, failed_files).
    """
    successful_ids = []
    failed_files = []
    
    try:
        # Create the batch
        file_ids = [item['file_id'] for item in batch]
        batch_upload = openai.beta.vector_stores.file_batches.create(
            vector_store_id=vector_store_id,
            file_ids=file_ids
        )
        
        # Poll for completion
        max_polls = 30
        poll_count = 0
        while poll_count < max_polls:
            batch_status = openai.beta.vector_stores.file_batches.retrieve(
                vector_store_id=vector_store_id,
                batch_id=batch_upload.id
            )
            
            if batch_status.status == "completed":
                console.print(f"[green]Batch upload completed: {batch_status.file_counts.completed} files[/green]")
                successful_ids.extend(file_ids)
                break
                
            elif batch_status.status == "failed":
                console.print(f"[red]Batch upload failed[/red]")
                # Add all files in the batch to failed files
                failed_files.extend([{
                    'name': item['name'],
                    'error': 'Batch upload failed'
                } for item in batch])
                # Clean up the failed files
                for file_id in file_ids:
                    try:
                        openai.files.delete(file_id)
                    except Exception as e:
                        console.print(f"[yellow]Failed to delete file {file_id}: {e}[/yellow]")
                break
            
            time.sleep(5)
            poll_count += 1
            console.print(f"[yellow]Waiting for batch completion... Attempt {poll_count}/{max_polls}[/yellow]")
        
        if poll_count >= max_polls:
            console.print("[red]Batch upload timed out[/red]")
            failed_files.extend([{
                'name': item['name'],
                'error': 'Batch upload timed out'
            } for item in batch])
            # Clean up the files
            for file_id in file_ids:
                try:
                    openai.files.delete(file_id)
                except Exception as e:
                    console.print(f"[yellow]Failed to delete file {file_id}: {e}[/yellow]")
    
    except Exception as e:
        console.print(f"[red]Error in batch upload: {e}[/red]")
        failed_files.extend([{
            'name': item['name'],
            'error': str(e)
        } for item in batch])
        # Clean up the files
        for file_id in file_ids:
            try:
                openai.files.delete(file_id)
            except Exception as delete_error:
                console.print(f"[yellow]Failed to delete file {file_id}: {delete_error}[/yellow]")
    
    return successful_ids, failed_files



def update_vector_store_stats(db, vector_store_id: str, success_count: int, failed_count: int, console: Console):
    """Update the vector store statistics in MongoDB."""
    try:
        db.vector_stores.update_one(
            {"vectorstore_idx": vector_store_id},
            {
                "$inc": {
                    "file_counts.completed": success_count,
                    "file_counts.failed": failed_count,
                    "file_counts.total": success_count + failed_count
                }
            }
        )
        console.print(f"[green]Updated vector store stats: +{success_count} completed, +{failed_count} failed[/green]")
    except Exception as e:
        console.print(f"[red]Error updating vector store stats: {e}[/red]")

def main():
    console = Console()
    console.print("[bold blue]Starting GitHub Repository Processing...[/bold blue]")
    
    try:
        github_token, mongo_uri = load_environment()
        
        # Initialize clients
        client = pymongo.MongoClient(mongo_uri)
        db = client.get_default_database()
        console.print("[green]Connected to MongoDB.[/green]")

        github_client = Github(github_token)
        console.print("[green]Initialized GitHub client.[/green]")

        # Create assistant if needed or use existing one
        # For now, we assume we have a known assistant_id. If needed, uncomment below.
        # assistant = create_assistant(console)
        # assistant_id = assistant.id
        assistant_id = "asst_hUjlVpcx3CKjAlvmFOgjjsbf"  # Existing assistant ID

        # Process users with GitHub links
        users = db.users.find({
            "$or": [
                {"github_link": {"$exists": True, "$ne": ""}},
                {"personal_website": {"$regex": "github.com", "$options": "i"}}
            ]
        })

        for user in users:
            user_id = str(user['_id'])
            github_link = user.get('github_link', '')
            personal_website = user.get('personal_website', '')
            
            # Get GitHub username
            if github_link:
                github_username = github_link.rstrip('/').split('/')[-1]
                github_url = github_link
            elif 'github.com' in personal_website.lower():
                github_username = personal_website.rstrip('/').split('/')[-1]
                github_url = personal_website
            else:
                console.print(f"[yellow]No valid GitHub link found for user with ID '{user_id}'. Skipping...[/yellow]")
                continue

            # Create/get vector store
            vector_store_id = create_user_vector_store(console, github_username, github_url, user_id, db)
            if not vector_store_id:
                console.print(f"[red]Could not create or retrieve a vector store for user {github_username}. Skipping this user.[/red]")
                continue

            # Process repositories
            try:
                user_data = github_client.get_user(github_username)
                all_files_data = []
                processed_repos = []
                total_files = 0

                for repo in user_data.get_repos():
                    try:
                        files_data = get_repository_files(
                            repo, user_id, github_username, 
                            repo.name, console, github_client
                        )
                        if files_data:
                            all_files_data.extend(files_data)
                            processed_repos.append(f"{repo.owner.login}/{repo.name}")
                            total_files += len(files_data)
                            console.print(f"[green]Collected {len(files_data)} files from {repo.owner.login}/{repo.name}[/green]")
                        time.sleep(0.1)  # Rate limit protection
                    except Exception as repo_error:
                        console.print(f"[red]Error processing repository {repo.full_name}: {repo_error}[/red]")
                        continue

                if all_files_data:
                    # Upload files to vector store
                    success_count, failed_files = upload_files_to_vector_store(
                        vector_store_id, all_files_data, console
                    )
                    
                    # Update statistics
                    update_vector_store_stats(
                        db, vector_store_id, 
                        success_count, len(failed_files),
                        console
                    )
                    
                    # Attach vector store to assistant
                    if success_count > 0:
                        try:
                            openai.beta.assistants.update(
                                assistant_id=assistant_id,
                                tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}}
                            )
                            console.print(f"[green]Attached vector store {vector_store_id} to assistant[/green]")
                        except Exception as e:
                            console.print(f"[red]Error attaching vector store to assistant: {e}[/red]")
                    
                    # Save vector store info
                    vector_store_info_saved = {
                        'user_id': user_id,
                        'github_username': github_username,
                        'github_url': github_url,
                        'vector_store_id': vector_store_id,
                        'file_count': {
                            'completed': success_count,
                            'failed': len(failed_files),
                            'total': success_count + len(failed_files)
                        },
                        'repositories': processed_repos,
                        'created_at': datetime.utcnow()
                    }
                    
                    output_file = save_vector_store_info([vector_store_info_saved])
                    console.print(f"\n[green]Info saved to: {output_file}[/green]")
                    
                    # Handle failed uploads
                    if failed_files:
                        console.print(f"[red]{len(failed_files)} files failed to upload.[/red]")
                        save_failed_uploads(failed_files, console)
                    else:
                        console.print("[yellow]No failed uploads to save for this user.[/yellow]")
                    
                    console.print(f"[green]Repositories processed for {github_username}: {', '.join(processed_repos)}[/green]")
                else:
                    console.print(f"[yellow]No files collected to upload for user {github_username}.[/yellow]")

            except UnknownObjectException:
                console.print(f"[red]GitHub user '{github_username}' not found.[/red]")
                continue
            except Exception as user_error:
                console.print(f"[red]Error processing user {github_username}: {user_error}[/red]")
                continue

        # Close MongoDB connection at the end
        client.close()
        console.print("[green]Closed MongoDB connection.[/green]")

    except Exception as e:
        console.print(f"[red]Critical error: {e}[/red]")
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
