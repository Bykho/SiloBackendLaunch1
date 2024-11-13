import os
import openai
from dotenv import load_dotenv
from pinecone import Pinecone
import argparse
from github import Github
import base64
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
from rich import print as rprint
import textwrap
from datetime import datetime

def load_environment():
    """Load environment variables from .env file."""
    load_dotenv()
    openai.api_key = os.getenv('OPENAI_API_KEY')
    pinecone_api_key = os.getenv("PINECONE_KEY")
    pinecone_env = os.getenv("PINECONE_ENV", "us-east-1")
    github_token = os.getenv('GITHUB_API_TOKEN')
    
    if not all([openai.api_key, pinecone_api_key, pinecone_env, github_token]):
        missing = []
        if not openai.api_key: missing.append("OPENAI_API_KEY")
        if not pinecone_api_key: missing.append("PINECONE_KEY")
        if not pinecone_env: missing.append("PINECONE_ENV")
        if not github_token: missing.append("GITHUB_API_TOKEN")
        raise ValueError(f"Missing environment variables: {', '.join(missing)}")
    
    return openai.api_key, pinecone_api_key, pinecone_env, github_token

def initialize_pinecone(api_key, environment):
    """Initialize Pinecone client and connect to the index."""
    pc = Pinecone(api_key=api_key)
    index_name = 'candidate-github-rag-test'
    
    if index_name not in pc.list_indexes().names():
        raise ValueError(f"Pinecone index '{index_name}' does not exist.")
    
    return pc.Index(index_name)

def get_query_embedding(query):
    """Generate embedding for the input query using OpenAI."""
    response = openai.Embedding.create(
        input=query,
        model='text-embedding-ada-002'
    )
    return response['data'][0]['embedding']

def search_pinecone(index, embedding, top_k=5):
    """Search Pinecone index for top_k similar vectors."""
    return index.query(
        vector=embedding,
        top_k=top_k,
        include_metadata=True
    )

def fetch_code_from_github(g, metadata, console):
    """
    Fetch code content from GitHub using the metadata.
    Returns tuple of (code_content, context_content, error_message)
    """
    try:
        username = metadata.get('username')
        repo_name = metadata.get('repo_name')
        file_path = metadata.get('file_path')
        function_name = metadata.get('function_name')
        related_functions = metadata.get('related_functions', [])
        
        # Get repository and file content
        repo = g.get_user(username).get_repo(repo_name)
        file_content = repo.get_contents(file_path)
        decoded_content = base64.b64decode(file_content.content).decode('utf-8')
        
        # If it's a README, return the whole file
        if metadata.get('type') == 'readme':
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
            is_def_line = any(f"{def_type} {name}" in line 
                            for def_type in ['def', 'class', 'function', 'const', 'let', 'var'] 
                            for name in [function_name] + related_functions)
            
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
        return None, None, f"Error fetching code: {str(e)}"

def create_results_directory():
    """Create a directory for storing search results if it doesn't exist."""
    results_dir = "search_results"
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
    return results_dir

def write_results_to_file(query, results, codes_and_contexts):
    """Write search results and retrieved code to a file."""
    results_dir = create_results_directory()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(results_dir, f"search_results_{timestamp}.txt")
    
    with open(filename, 'w', encoding='utf-8') as f:
        # Write search query
        f.write("Search Query:\n")
        f.write("=" * 80 + "\n")
        f.write(f"{query}\n\n")
        
        # Write results
        for idx, (match, (code, context)) in enumerate(zip(results['matches'], codes_and_contexts), 1):
            metadata = match.metadata
            
            # Write metadata
            f.write(f"\nResult {idx}:\n")
            f.write("-" * 80 + "\n")
            f.write(f"File: {metadata.get('file_path', 'Unknown File')}\n")
            f.write(f"Function: {metadata.get('function_name', 'N/A')}\n")
            f.write(f"Repository: {metadata.get('username', 'N/A')}/{metadata.get('repo_name', 'N/A')}\n")
            f.write(f"Match Score: {match.score:.3f}\n\n")
            
            # Write context if available
            if context:
                f.write("Context:\n")
                f.write("-" * 40 + "\n")
                f.write(f"{context}\n\n")
            
            # Write code content
            f.write("Code:\n")
            f.write("-" * 40 + "\n")
            if code:
                f.write(f"{code}\n")
            else:
                f.write("No code content available.\n")
            
            f.write("\n" + "=" * 80 + "\n")
    
    return filename

def display_result(console, idx, match, code_content, context_content):
    """Display a single search result with syntax highlighting."""
    metadata = match.metadata
    file_path = metadata.get('file_path', 'Unknown File')
    function_name = metadata.get('function_name', 'N/A')
    username = metadata.get('username', 'N/A')
    repo_name = metadata.get('repo_name', 'N/A')
    
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
        Match Score: {match.score:.3f}
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
        # Load environment variables and initialize clients
        _, pinecone_api_key, pinecone_env, github_token = load_environment()
        index = initialize_pinecone(pinecone_api_key, pinecone_env)
        g = Github(github_token)
        
        # Generate embedding and search
        console.print("🔍 Searching for relevant code...\n")
        embedding = get_query_embedding(args.query)
        results = search_pinecone(index, embedding, top_k=15)
        
        if not results['matches']:
            console.print("No results found.")
            return
        
        # Store all code and context for file writing
        codes_and_contexts = []
            
        # Display results and collect code
        for idx, match in enumerate(results['matches'], 1):
            code_content, context_content, error = fetch_code_from_github(g, match.metadata, console)
            codes_and_contexts.append((code_content, context_content))
            
            if error:
                console.print(f"[red]Error for result {idx}: {error}[/red]\n")
                continue
                
            display_result(console, idx, match, code_content, context_content)
        
        # Write results to file
        output_file = write_results_to_file(args.query, results, codes_and_contexts)
        console.print(f"\n[green]Results have been saved to: {output_file}[/green]")
            
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")

if __name__ == '__main__':
    main()