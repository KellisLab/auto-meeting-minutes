import os
import openai
import logging
import json
from collections import defaultdict
from dotenv import load_dotenv
from utils import parse_json

# Load environment variables
load_dotenv()
logger = logging.getLogger(__name__)

def generate_standup_summary(commits, date_str, api_key=None):
    """
    Sends commit data to LLM to generate a structured JSON standup report.
    Batches commits by Repository -> Date -> Author.
    """
    if not commits:
        return {"results": {}}

    # Use provided key or env var
    key = api_key or os.getenv("API_KEY")
    if not key:
        logger.error("No OpenAI API Key provided")
        return {"results": {"Error": {"summary": "No API Key provided", "authors": [], "type": "Error"}}}
    
    # Configure OpenAI client
    base_url = os.getenv("AI_BASE_URL")
    if base_url:
        client = openai.OpenAI(api_key=key, base_url=base_url)
    else:
        client = openai.OpenAI(api_key=key)

    model = os.getenv("GPT_MODEL", "gpt-4o")

    # 1. Group commits: Repo -> Date -> Author
    grouped_data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    
    for c in commits:
        repo = c.get('repo', 'Unknown')
        # Extract YYYY-MM-DD from ISO timestamp
        ts = c.get('timestamp', '')
        date_key = ts.split('T')[0] if 'T' in ts else (ts or 'Unknown Date')
        author = c.get('author', 'Unknown')
        
        grouped_data[repo][date_key][author].append(c)
        logger.info(c)
    #endfor
    all_results = {}

    # 2. Process each batch
    # Hierarchy: Repository -> Date -> Person
    for repo, dates in grouped_data.items():
        for date, authors in dates.items():
            for author, author_commits in authors.items():
                
                logger.info(f"Processing batch: {repo} | {date} | {author} ({len(author_commits)} commits)")
                
                batch_response = process_single_batch(client, model, repo, date, author, author_commits)
                
                # 3. Merge results
                if batch_response and 'results' in batch_response:
                    for task_title, details in batch_response['results'].items():
                        # Create a unique key to prevent overwriting similar task names from other repos
                        # We prepend the Repo name to the task title for clarity in the final report
                        unique_title = f"[{repo}] {task_title}"
                        
                        # Ensure the author is listed (in case LLM missed it)
                        if author not in details.get('authors', []):
                            details.setdefault('authors', []).append(author)
                            
                        all_results[unique_title] = details

    return {"results": all_results}

def process_single_batch(client, model, repo, date, author, commits):
    """
    Helper function to summarize a specific batch of commits.
    """
    # Prepare Context
    context_text = f"Context: Repository '{repo}' on {date} by Author '{author}'\n\n"
    
    for i, c in enumerate(commits):
        context_text += f"Commit {i+1}:\n"
        context_text += f"Message: {c.get('message', 'No message')}\n"
        
        # Add file stats summary
        if 'file_stats' in c and c['file_stats']:
            files_changed = [f"{fs['filename']}" for fs in c['file_stats']]
            context_text += f"Files: {', '.join(files_changed[:10])}\n"
            
        # Add the actual diff (truncated)
        diff = c.get('diff', '')
        
        context_text += f"Changes:\n{diff}\n"
        context_text += "-" * 40 + "\n"

    # Define Prompt
    system_prompt = """
    You are a Technical Summarizer. Analyze the provided git commits for a specific developer in a specific repository.
    
    Goal: Create a structured JSON summary of the work performed.
    
    Guidelines:
    1. Group the commits into logical **Tasks** (e.g., "Auth Refactor", "Fix Login Bug").
    2. Provide a technical summary of WHAT changed and HOW.
    3. Identify the type of work (Feature, Bugfix, Refactor, Chore, Documentation).
    4. The 'authors' list must include the author provided in the context.
    
    Output Format (Strict JSON):
    {
        "results": {
            "<Task Title>": {
                "authors": ["<Author Name>"],
                "summary": "<Technical summary>",
                "type": "<Feature|Bugfix|Refactor|Chore|Docs>"
            }
        }
    }
    """

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context_text}
            ],
            temperature=0.3, 
            max_tokens=1000,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        return json.loads(content)

    except Exception as e:
        logger.error(f"Error processing batch {repo}/{date}/{author}: {e}")
        return {}

def generate_git_html(summary_data, date_str, repo_urls, output_file):
    """
    Generates an HTML report from the structured summary data.
    """
    # Safety check for summary_data type
    if not isinstance(summary_data, dict):
        logger.error(f"generate_git_html received {type(summary_data)} instead of dict")
        summary_data = {"results": {}}

    results = summary_data.get("results", {})
    
    html_content = "<!DOCTYPE html>\n<html>\n<head>\n<title>Activity Report</title>\n"
    html_content += "<style>\n"
    html_content += "body { font-family: Arial, sans-serif; margin: 20px; font-size: 11pt; background-color: #f9f9f9; }\n"
    html_content += ".container { max-width: 900px; margin: 0 auto; background: white; padding: 30px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }\n"
    html_content += "h1 { font-family: Cambria, serif; font-size: 18pt; color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px; }\n"
    html_content += ".meta { color: #7f8c8d; font-size: 0.9em; margin-bottom: 20px; }\n"
    html_content += "ol { list-style-position: outside; padding-left: 20px; }\n"
    html_content += "li { margin-bottom: 15px; }\n"
    html_content += "h3.topic-heading { font-family: Arial, sans-serif; font-size: 12pt; color: #2980b9; margin: 0 0 5px 0; }\n"
    html_content += ".type-tag { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; color: white; margin-left: 8px; vertical-align: middle; }\n"
    html_content += ".tag-Feature { background-color: #27ae60; }\n"
    html_content += ".tag-Bugfix { background-color: #c0392b; }\n"
    html_content += ".tag-Refactor { background-color: #f39c12; }\n"
    html_content += ".tag-Chore { background-color: #7f8c8d; }\n"
    html_content += ".tag-Docs { background-color: #8e44ad; }\n"
    html_content += ".authors { font-size: 0.9em; color: #666; font-style: italic; }\n"
    html_content += ".topic-content { margin-top: 5px; line-height: 1.5; color: #333; }\n"
    html_content += "a { color: #2980b9; text-decoration: none; }\n"
    html_content += "a:hover { text-decoration: underline; }\n"
    html_content += "</style>\n</head>\n<body>\n"
    
    html_content += f'<div class="container">\n'
    html_content += f'<h1>Activity Report: {date_str}</h1>\n'
    
    if repo_urls:
        if isinstance(repo_urls, str):
            repo_urls = [repo_urls]
            
        html_content += '<div class="meta">Repositories: '
        links = []
        for url in repo_urls:
            links.append(f'<a href="{url}">{url}</a>')
        html_content += ", ".join(links)
        html_content += '</div>\n'
    
    html_content += "<ol>\n"
    
    # Sort results by Repo name (which is part of the key now)
    sorted_keys = sorted(results.keys())
    
    for title in sorted_keys:
        details = results[title]
        summary = details.get("summary", "")
        authors = details.get("authors", [])
        work_type = details.get("type", "Other")
        
        authors_str = ", ".join(authors) if authors else "Unknown"
        
        html_content += '<li>'
        html_content += f'<h3 class="topic-heading">{title}'
        html_content += f'<span class="type-tag tag-{work_type}">{work_type}</span>'
        html_content += '</h3>'
        
        html_content += f'<div class="authors">Contributors: {authors_str}</div>'
        html_content += f'<div class="topic-content">{summary}</div>'
        html_content += '</li>\n'

    html_content += "</ol>\n</div>\n</body>\n</html>"

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    return output_file

def generate_git_markdown(summary_data, date_str, output_file):
    """
    Generates a Markdown report from the structured summary data.
    """
    # Safety check for summary_data type
    if not isinstance(summary_data, dict):
        summary_data = {"results": {}}

    results = summary_data.get("results", {})
    
    md_lines = []
    md_lines.append(f"# Activity Report - {date_str}\n")
    
    sorted_keys = sorted(results.keys())
    
    for title in sorted_keys:
        details = results[title]
        summary = details.get("summary", "")
        authors = details.get("authors", [])
        work_type = details.get("type", "Other")
        
        authors_str = ", ".join(authors) if authors else "Unknown"
        
        md_lines.append(f"### {title} `[{work_type}]`")
        md_lines.append(f"**Contributors:** {authors_str}\n")
        md_lines.append(f"{summary}\n")
        md_lines.append("---\n")
        
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
        
    return output_file