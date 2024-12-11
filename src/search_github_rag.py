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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple, Optional

# Import MongoDB
from . import mongo  # Adjust based on your project structure

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

def create_assistant(client, name: str, instructions: str, model: str) -> str:
    """Create an Assistant via the OpenAI SDK."""
    try:
        assistant = client.beta.assistants.create(
            name=name,
            instructions=instructions,
            model=model,
            tools=[{"type": "file_search"}]
        )
        logger.info(f"Created new assistant: {assistant.id}")
        return assistant.id
    except Exception as e:
        logger.error(f"Error creating assistant: {e}")
        raise

def create_thread(client) -> str:
    """Create a Thread."""
    try:
        thread = client.beta.threads.create()
        logger.info(f"Created thread: {thread.id}")
        return thread.id
    except Exception as e:
        logger.error(f"Error creating thread: {e}")
        raise

def get_or_create_thread(client, user_id: str) -> str:
    """Retrieve an existing thread for the user or create a new one."""
    try:
        # Check for an existing thread
        thread_record = mongo.db.threads.find_one({"user_id": user_id})
        
        if thread_record:
            try:
                # Verify the thread still exists in OpenAI
                client.beta.threads.retrieve(thread_record['thread_id'])
                logger.info(f"Using existing thread {thread_record['thread_id']} for user {user_id}")
                return thread_record['thread_id']
            except Exception as e:
                # Thread doesn't exist in OpenAI, create a new one
                logger.warning(f"Thread not found in OpenAI for user {user_id}, creating new thread")
                mongo.db.threads.delete_one({"_id": thread_record['_id']})
        
        # Create a new thread
        new_thread_id = create_thread(client)
        
        # Store the association
        mongo.db.threads.insert_one({
            "user_id": user_id,
            "thread_id": new_thread_id,
            "created_at": datetime.utcnow()
        })
        
        logger.info(f"Created new thread {new_thread_id} for user {user_id}")
        return new_thread_id
        
    except Exception as e:
        logger.error(f"Error in get_or_create_thread for user {user_id}: {e}")
        raise

def add_message_to_thread(client, thread_id: str, role: str, content: str) -> str:
    """Add a message to a Thread."""
    try:
        message = client.beta.threads.messages.create(
            thread_id=thread_id,
            role=role,
            content=content
        )
        logger.info(f"Added message to thread {thread_id}")
        return message.id
    except Exception as e:
        logger.error(f"Error adding message to thread: {e}")
        raise

def run_assistant(client, thread_id: str, assistant_id: str, instructions: Optional[str] = None) -> str:
    """Run the Assistant on the specified Thread."""
    try:
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
            instructions=instructions
        )
        logger.info(f"Created run {run.id} for thread {thread_id}")
        return run.id
    except Exception as e:
        logger.error(f"Error creating run: {e}")
        raise

def poll_run_status(client, thread_id: str, run_id: str, timeout: int = 300, interval: int = 1) -> Tuple:
    """Poll the Run status until completion or timeout."""
    try:
        start_time = time.time()
        while True:
            run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
            logger.info(f"Run status: {run.status}")
            
            if run.status == 'completed':
                messages = client.beta.threads.messages.list(thread_id=thread_id)
                return run, messages
                
            elif run.status == 'requires_action':
                error_msg = f"Run {run_id} requires action"
                if run.required_action:
                    error_msg += f": {run.required_action}"
                raise ValueError(error_msg)
                
            elif run.status in ['failed', 'cancelled', 'expired']:
                error_msg = f"Run {run_id} ended with status: {run.status}"
                if run.last_error:
                    error_msg += f", Error: {run.last_error}"
                raise ValueError(error_msg)
                
            elif run.status not in ['queued', 'in_progress', 'cancelling']:
                raise ValueError(f"Run {run_id} has unexpected status: {run.status}")
                
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Polling timed out after {timeout} seconds")
                
            time.sleep(interval)
            
    except Exception as e:
        logger.error(f"Error polling run status: {e}")
        raise

def attach_vector_store(client, assistant_id: str, vector_store_idx: str):
    """Attach a vector store to the assistant."""
    try:
        client.beta.assistants.update(
            assistant_id=assistant_id,
            tool_resources={"file_search": {"vector_store_ids": [vector_store_idx]}}
        )
        logger.info(f"Attached vector store {vector_store_idx} to assistant {assistant_id}")
        time.sleep(1)  # Wait for attachment to take effect
    except Exception as e:
        logger.error(f"Error attaching vector store: {e}")
        raise

def detach_vector_store(client, assistant_id: str):
    """Detach all vector stores from the assistant."""
    try:
        client.beta.assistants.update(
            assistant_id=assistant_id,
            tool_resources={"file_search": {"vector_store_ids": []}}
        )
        logger.info(f"Detached vector stores from assistant {assistant_id}")
    except Exception as e:
        logger.error(f"Error detaching vector store: {e}")
        raise

def extract_search_results(run_output: Tuple, skill: str) -> List[Dict]:
    """
    Extract search results from the assistant's response and format with skill context.
    Now includes the skill that was searched for in each match.
    """
    try:
        _, messages = run_output
        
        # Get last assistant message
        assistant_messages = [msg for msg in messages if msg.role == 'assistant']
        if not assistant_messages:
            return []
            
        last_message = assistant_messages[-1]
        content = last_message.content[0].text.value if isinstance(last_message.content, list) else last_message.content
        
        logger.info(f"Raw response content: {content}")
        
        # Extract JSON from content
        try:
            # Try to parse as plain JSON first
            data = json.loads(content)
        except json.JSONDecodeError:
            # If that fails, try to extract JSON from markdown
            if '```json' in content:
                json_content = content.split('```json')[1].split('```')[0].strip()
                data = json.loads(json_content)
            else:
                logger.error("Could not extract JSON from response")
                return []
        
        if 'matches' in data:
            matches = data['matches']
            # Add skill context to each match
            formatted_matches = []
            for match in matches:
                formatted_matches.append({
                    'skill': skill,
                    'file_path': match.get('file_path', ''),
                    'explanation': match.get('explanation', '')
                })
            logger.info(f"Found {len(formatted_matches)} matches for skill {skill}")
            return formatted_matches
        
        return []
    
    except Exception as e:
        logger.error(f"Error extracting search results: {e}")
        return []

def search_with_retries(client, thread_id: str, assistant_id: str, vector_store_idx: str, skill: str, max_retries: int = 3) -> List[Dict]:
    """Search for a skill with retries and exponential backoff using an existing thread."""
    retry_count = 0
    base_delay = 2
    
    while retry_count < max_retries:
        try:
            # Add message to thread
            add_message_to_thread(client, thread_id, "user", f"Search for code related to: {skill}")
            
            # Create and wait for run to complete
            run_id = run_assistant(client, thread_id, assistant_id)
            run_output = poll_run_status(client, thread_id, run_id)
            
            # Extract results before cleaning up
            results = extract_search_results(run_output, skill)  # Pass skill to extract_search_results
            
            # Clean up messages
            try:
                messages = client.beta.threads.messages.list(thread_id=thread_id)
                for msg in messages.data:
                    try:
                        client.beta.threads.messages.delete(thread_id=thread_id, message_id=msg.id)
                    except Exception as e:
                        logger.warning(f"Failed to delete message {msg.id}: {e}")
                        continue
                logger.info(f"Cleaned up messages for thread {thread_id}")
            except Exception as e:
                logger.warning(f"Failed to clean thread messages: {e}")
            
            return results

        except Exception as e:
            retry_count += 1
            if retry_count == max_retries:
                logger.error(f"Failed after {max_retries} attempts for skill '{skill}': {e}")
                return []

            delay = base_delay * (2 ** (retry_count - 1))
            logger.warning(f"Attempt {retry_count} failed for skill '{skill}', retrying in {delay} seconds...")
            time.sleep(delay)
            
    return []

def process_vector_store(client, assistant_id: str, store: Dict, skills: List[str]) -> Tuple[str, Dict]:
    """Process a single vector store with proper error handling and rate limiting."""
    user_id = store.get('user_id')
    vector_store_idx = store.get('vectorstore_idx')
    
    if not user_id or not vector_store_idx:
        raise ValueError(f"Missing required fields in store: {store}")
        
    logger.info(f"Processing vector store {vector_store_idx} for user {user_id}")
    results = {'matches': [], 'skills_matched': set()}
    
    try:
        # Get or create thread
        thread_id = get_or_create_thread(client, user_id)
        logger.info(f"Using thread {thread_id} for user {user_id}")
        
        # Attach vector store
        attach_vector_store(client, assistant_id, vector_store_idx)
        logger.info(f"Attached vector store {vector_store_idx}")
        
        # Process skills sequentially within each vector store
        for skill in skills:
            try:
                matches = search_with_retries(
                    client,
                    thread_id,
                    assistant_id,
                    vector_store_idx,
                    skill
                )
                
                if matches:
                    results['matches'].extend(matches)
                    results['skills_matched'].add(skill)
                    logger.info(f"Found matches for skill '{skill}'")
                
                # Add delay between skills
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error processing skill '{skill}': {e}")
                continue
    
    except Exception as e:
        logger.error(f"Error processing vector store {vector_store_idx}: {e}")
        raise
    finally:
        try:
            detach_vector_store(client, assistant_id)
            logger.info(f"Detached vector store {vector_store_idx}")
        except Exception as e:
            logger.error(f"Error detaching vector store {vector_store_idx}: {e}")
    
    return user_id, results

def search_across_stores(client, assistant_id: str, vector_stores: List[Dict], skills: List[str], max_workers: int = 3) -> Dict:
    """
    Coordinate searching across all vector stores in parallel with proper error handling.
    
    Args:
        client: OpenAI client instance
        assistant_id: ID of the assistant to use
        vector_stores: List of vector store configurations
        skills: List of skills to search for
        max_workers: Maximum number of concurrent threads (default: 3)
    
    Returns:
        Dict containing search results for each user
    """
    results = {}
    total_stores = len(vector_stores)
    completed_stores = 0
    
    # Using ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks to the executor
        future_to_store = {
            executor.submit(
                process_vector_store,
                client,
                assistant_id,
                store,
                skills
            ): store for store in vector_stores
        }
        
        # Process completed futures as they finish
        for future in as_completed(future_to_store):
            store = future_to_store[future]
            try:
                user_id, store_results = future.result()
                results[user_id] = store_results
                completed_stores += 1
                logger.info(f"Completed processing for user {user_id} ({completed_stores}/{total_stores})")
                time.sleep(2)  # Add delay between vector stores
                
            except Exception as e:
                logger.error(f"Error processing store for user {store['user_id']}: {e}")
                continue
    
    return results

def create_results_directory() -> str:
    """Create a directory for storing search results."""
    results_dir = "search_results"
    os.makedirs(results_dir, exist_ok=True)
    return results_dir

def write_results_to_file(query: str, results: Dict) -> str:
    """Write search results to a JSON file."""
    results_dir = create_results_directory()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(results_dir, f"search_results_{timestamp}.json")
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump({
            'query': query,
            'results': results
        }, f, indent=2)
    
    return filename
