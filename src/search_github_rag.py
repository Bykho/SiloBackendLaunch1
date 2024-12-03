import os
import openai
from dotenv import load_dotenv
import argparse
from github import Github
import base64
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
import textwrap
from datetime import datetime
import json
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_environment():
    """Load environment variables from .env file."""
    load_dotenv()
    openai_api_key = os.getenv('OPENAI_API_KEY')
    github_token = os.getenv('GITHUB_API_TOKEN')
    
    if not all([openai_api_key, github_token]):
        missing = []
        if not openai_api_key: missing.append("OPENAI_API_KEY")
        if not github_token: missing.append("GITHUB_API_TOKEN")
        raise ValueError(f"Missing environment variables: {', '.join(missing)}")
    
    openai.api_key = openai_api_key
    return github_token

def create_assistant(client, name, instructions, model):
    """
    Create an Assistant via the OpenAI SDK.
    """
    try:
        assistant = client.beta.assistants.create(
            name=name,
            instructions=instructions,
            model=model
        )
        return assistant.id
    except Exception as e:
        logger.error(f"Error creating assistant: {e}")
        raise e

def create_thread(client, assistant_id):
    """
    Create a Thread.
    """
    try:
        thread = client.beta.threads.create()
        return thread.id
    except Exception as e:
        logger.error(f"Error creating thread: {e}")
        raise e

def add_message_to_thread(client, thread_id, role, content):
    """
    Add a message to a Thread.
    """
    try:
        message = client.beta.threads.messages.create(
            thread_id=thread_id,
            role=role,
            content=content
        )
        return message.id
    except Exception as e:
        logger.error(f"Error adding message to thread: {e}")
        raise e

def run_assistant(client, thread_id, assistant_id, instructions=None):
    """
    Run the Assistant on the specified Thread.
    """
    try:
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
            instructions=instructions
        )
        return run.id
    except Exception as e:
        logger.error(f"Error creating run: {e}")
        raise e

def poll_run_status(client, thread_id, run_id, timeout=300, interval=5):
    """
    Poll the Run status until completion or timeout.
    
    Args:
        client: OpenAI client instance
        thread_id: ID of the thread
        run_id: ID of the run to poll
        timeout: Maximum time to poll in seconds (default: 300)
        interval: Time between polling attempts in seconds (default: 5)
        
    Returns:
        tuple: (run object, list of messages)
        
    Raises:
        ValueError: If the run fails, is cancelled, or requires action
        TimeoutError: If polling exceeds the timeout period
    """
    try:
        start_time = time.time()
        while True:
            run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
            logger.info(f"Run status: {run.status}")
            
            if run.status == 'completed':
                # Fetch messages after completion
                messages = client.beta.threads.messages.list(thread_id=thread_id)
                return run, messages
            elif run.status == 'requires_action':
                if run.required_action:
                    raise ValueError(f"Run {run_id} requires action: {run.required_action}")
                else:
                    raise ValueError(f"Run {run_id} requires action but no action specified")
            elif run.status in ['failed', 'cancelled', 'expired']:
                error_msg = f"Run {run_id} ended with status: {run.status}"
                if run.last_error:
                    error_msg += f", Error: {run.last_error}"
                if run.status == 'incomplete' and run.incomplete_details:
                    error_msg += f", Details: {run.incomplete_details}"
                raise ValueError(error_msg)
            elif run.status not in ['queued', 'in_progress', 'cancelling']:
                raise ValueError(f"Run {run_id} has unexpected status: {run.status}")
                
            elapsed = time.time() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"Polling timed out after {timeout} seconds")
                
            time.sleep(interval)
            
    except Exception as e:
        logger.error(f"Error polling run status: {e}")
        raise

def validate_json_response(content):
    """
    Validate that the content is a JSON with the required structure.
    """
    try:
        data = json.loads(content)
        if 'matches' not in data:
            logger.error("JSON response does not contain 'matches' key.")
            return False
        for match in data['matches']:
            required_keys = ['file_path', 'repository_name', 'github_username', 'function_name', 'score', 'explanation']
            if not all(key in match for key in required_keys):
                logger.error(f"Match missing required keys: {match}")
                return False
        return True
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON response: {e}")
        return False

def extract_search_results(run_output, threshold):
    """
    Extract and group search results by user_id based on threshold.
    """
    try:
        _, messages = run_output
        
        # Get all assistant messages
        assistant_messages = [msg for msg in messages if msg.role == 'assistant']
        if not assistant_messages:
            logger.info("No assistant messages found.")
            return {}
            
        last_message = assistant_messages[-1]
        content = last_message.content[0].text.value if isinstance(last_message.content, list) else last_message.content
        logger.info(f"Message content: {content}")
        
        # Validate JSON
        if not validate_json_response(content):
            logger.error("JSON response validation failed.")
            return {}
        
        data = json.loads(content)
        matches = [m for m in data.get('matches', []) if m.get('score', 0) >= threshold]
        logger.info(f"Filtered to {len(matches)} matches with score >= {threshold}.")

        # Aggregate by user_id
        aggregated = {}
        for match in matches:
            encoded_path = match.get('file_path', '')
            user_id = encoded_path.split('_')[0] if '_' in encoded_path else 'unknown_user'
            if user_id not in aggregated:
                aggregated[user_id] = {
                    'user_id': user_id,
                    'github_username': match.get('github_username', 'N/A'),
                    'matches': []
                }
            aggregated[user_id]['matches'].append(match)
        
        return aggregated
    
    except Exception as e:
        logger.error(f"Error extracting search results: {e}")
        raise ValueError(f"Error processing assistant response: {str(e)}")


def fetch_code_from_github(g, metadata, console):
    """
    Fetch code content from GitHub using the metadata.
    Returns tuple of (code_content, context_content, error_message)
    """
    try:
        username = metadata.get('github_username')
        repo_name = metadata.get('repository_name')
        file_path = metadata.get('file_path')
        function_name = metadata.get('function_name', 'N/A')
        
        if not all([username, repo_name, file_path]):
            logger.error(f"Missing metadata fields. Received metadata: {metadata}")
            return None, None, "Incomplete metadata for fetching code."
        
        # Hardcode branch selection
        if repo_name == "SiloBackendLaunch1":
            branch = "Development"
        else:
            branch = "main"
        
        # Get repository and file content
        repo = g.get_repo(f"{username}/{repo_name}")
        file_content = repo.get_contents(file_path, ref=branch)
        decoded_content = base64.b64decode(file_content.content).decode('utf-8')
        
        # If it's a README, return the whole file
        if os.path.basename(file_path).lower() == 'readme.md':
            return decoded_content, None, None
            
        # Split into lines for processing
        lines = decoded_content.split('\n')
        
        # Initialize result containers
        main_content = []
        context_content = []
        in_target = False
        current_function = None
        bracket_count = 0
        
        # Process line by line
        for line in lines:
            # Check for function/class definitions
            is_def_line = False
            if function_name != 'N/A':
                is_def_line = any(
                    f"{def_type} {function_name}" in line 
                    for def_type in ['def', 'class', 'function', 'const', 'let', 'var']
                )
            
            if is_def_line:
                in_target = True
                current_function = line
                bracket_count = line.count('{') - line.count('}')
                main_content.append(line)
            elif in_target:
                bracket_count += line.count('{') - line.count('}')
                main_content.append(line)
                
                # Check if we've reached the end of the function
                if bracket_count <= 0 and line.strip() == '' and current_function:
                    in_target = False
                    current_function = None
            else:
                # Store potential context (imports, global variables, etc.)
                if any(context_item in line for context_item in ['import ', 'from ', 'require', 'const ', 'let ', 'var ']):
                    context_content.append(line)

        main_code = '\n'.join(main_content)
        context = '\n'.join(context_content) if context_content else None
        
        return main_code, context, None
            
    except Exception as e:
        logger.error(f"Error fetching code from GitHub: {e}")
        return None, None, f"Error fetching code: {str(e)}"

def create_results_directory():
    """Create a directory for storing search results if it doesn't exist."""
    results_dir = "search_results"
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
    return results_dir

def write_results_to_file(query, aggregated_matches):
    """Write aggregated search results to a JSON file."""
    results_dir = create_results_directory()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(results_dir, f"search_results_{timestamp}.json")
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump({
            'query': query,
            'results': aggregated_matches
        }, f, indent=2)
    
    return filename


def display_result(console, idx, match, code_content, context_content):
    """Display a single search result with syntax highlighting."""
    file_path = match.get('file_path', 'Unknown File')
    function_name = match.get('function_name', 'N/A')
    username = match.get('github_username', 'N/A')
    repo_name = match.get('repository_name', 'N/A')
    
    # Determine the language for syntax highlighting
    extension = os.path.splitext(file_path)[1][1:]
    if extension in ['js', 'jsx', 'ts', 'tsx']:
        language = 'javascript'
    elif extension == 'py':
        language = 'python'
    else:
        language = extension if extension else 'text'

    # Create header with metadata
    header = f"Result {idx}"
    metadata_text = textwrap.dedent(f"""
        File: {file_path}
        Function: {function_name}
        Repository: {username}/{repo_name}
        Match Score: {match.get('score', 0):.3f}
    """)
    
    # Display the result in a panel
    console.print(Panel(metadata_text, title=header, title_align="left"))
    
    # Display context if available
    if context_content:
        console.print("Context:")
        console.print(Syntax(context_content, language, theme="monokai", line_numbers=True))
    
    # Display main code content
    if code_content:
        console.print("Code:")
        console.print(Syntax(code_content, language, theme="monokai", line_numbers=True))
    
    console.print("\n")


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Search GitHub RAG for relevant files.")
    parser.add_argument('query', type=str, help='Search query')
    args = parser.parse_args()
    
    # Initialize console for rich output
    console = Console()
    
    try:
        # Load environment variables and initialize GitHub client
        github_token = load_environment()
        g = Github(github_token)
        
        # Initialize OpenAI client
        client = openai.OpenAI(api_key=openai.api_key)
        
        # Define your assistant_id and vector_store_id (replace with your actual IDs)
        assistant_id = "asst_hUjlVpcx3CKjAlvmFOgjjsbf"
        vector_store_id = "vs_uOiITYpmod1DxYVABOVaC8Xj"  # Your existing vector store ID
        
        # Step 1: Create a Thread
        console.print("🔍 Creating a thread with your query...\n")
        thread_id = create_thread(client, assistant_id)
        console.print(f"✅ Created thread with ID: {thread_id}\n")
        
        # Step 2: Add Message to Thread
        console.print("✍️ Adding your query to the thread...\n")
        add_message_to_thread(client, thread_id, role="user", content=args.query)
        console.print("✅ Added message to thread.\n")
        
        # Step 3: Create a Run on the Thread
        instructions = """
        Provide your response in a JSON format with a key called "matches". Each match should be an object containing the following fields:
        - file_path: The path to the file in the repository (e.g., "backend/models.py").
        - repository_name: The name of the GitHub repository (e.g., "SiloBackendLaunch1").
        - github_username: The GitHub username of the repository owner (e.g., "Bykho").
        - function_name: The name of the function if applicable (e.g., "get_user"). Use "N/A" if not applicable.
        - score: A relevance score between 0 and 1 (e.g., 0.95).
        - explanation: A brief explanation of how this file relates to the query.
        
        **Important:** Do not include any additional text or explanations outside the JSON object. The entire response should be valid JSON only.
        
        Example Response:
        {
            "matches": [
                {
                    "file_path": "backend/models.py",
                    "repository_name": "SiloBackendLaunch1",
                    "github_username": "Bykho",
                    "function_name": "get_user",
                    "score": 0.95,
                    "explanation": "This function handles user retrieval from the database, which is relevant to managing relational databases."
                },
                {
                    "file_path": "frontend/app.js",
                    "repository_name": "SiloFrontendLaunch1",
                    "github_username": "Bykho",
                    "function_name": "initializeApp",
                    "score": 0.90,
                    "explanation": "Initializes the application and connects to MongoDB, demonstrating non-relational database usage."
                }
            ]
        }
        """
        console.print("🛠️ Creating a run on the thread...\n")
        run_id = run_assistant(client, thread_id, assistant_id, instructions)
        console.print(f"✅ Created run with ID: {run_id}\n")
        
        # Step 4: Poll the Run Status until completion
        console.print("🔄 Polling run status...")
        run_and_messages = poll_run_status(client, thread_id, run_id)
        console.print("✅ Run completed.\n")
        
        # Step 5: Extract and Aggregate search results
        threshold = 0.4  # Similarity score threshold
        aggregated_matches = extract_search_results(run_and_messages, threshold)

        if not aggregated_matches:
            console.print("ℹ️ No relevant file matches found in the response.")
            # Optionally display assistant's message
            return

        # Step 6: Process aggregated matches for scoring
        for user_id, user_data in aggregated_matches.items():
            scores = [match['score'] for match in user_data['matches']]
            user_data['total_score'] = sum(scores) / len(scores) if scores else 0

        # Step 7: Display aggregated results and collect codes
        console.print(f"📄 Displaying results for {len(aggregated_matches)} users:\n")
        for idx, (user_id, user_data) in enumerate(aggregated_matches.items(), 1):
            console.print(f"[bold green]User {idx}: {user_data['github_username']} (ID: {user_id})[/bold green]")
            console.print(f"Total Score: {user_data['total_score']:.2f}\n")
            for match_idx, match in enumerate(user_data['matches'], 1):
                code_content, context_content, error = fetch_code_from_github(g, match, console)
                if error:
                    console.print(f"[red]Error for match {match_idx}: {error}[/red]\n")
                    continue
                display_result(console, match_idx, match, code_content, context_content)
            console.print("\n" + "=" * 80 + "\n")

        # Step 8: Write aggregated results to file
        output_file = write_results_to_file(args.query, aggregated_matches)
        console.print(f"\n✅ Aggregated results have been saved to: {output_file}")
            
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")


if __name__ == '__main__':
    main()
