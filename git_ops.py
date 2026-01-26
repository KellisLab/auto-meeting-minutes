import os
import requests
import logging
from datetime import datetime
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def parse_github_url(url):
    
    parsed = urlparse(url)
    path_parts = parsed.path.strip("/").split("/")
    
    if len(path_parts) >= 2:
        owner = path_parts[0]
        repo = path_parts[1].replace(".git", "")
        return owner, repo
    return None, None

def fetch_repo_changes(repo_url, username, start_date, end_date=None, token=None):
    
    owner, repo = parse_github_url(repo_url)
    if not owner or not repo:
        logger.error(f"Invalid GitHub URL: {repo_url}")
        return []

    # 1. Setup API headers
    headers = {
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Check for token in args or env var
    api_token = token or os.getenv("GITHUB_TOKEN")
    if api_token:
        headers["Authorization"] = f"token {api_token}"
    else:
        logger.warning("No GITHUB_TOKEN found. Private repositories will return 404.")
    
    # 2. Define time range
    # If end_date is not provided, assume single day (start_date)
    target_end = end_date if end_date else start_date
    
    since_date = f"{start_date}T00:00:00Z"
    until_date = f"{target_end}T23:59:59Z"
    
    params = {
        "since": since_date,
        "until": until_date,
        "per_page": 100  # Maximum allowed by GitHub API
    }
    
    if username:
        params["author"] = username

    # 3. Get List of Commits with Pagination
    commits_url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    logger.info(f"Fetching commits from {commits_url} for range {start_date} to {target_end}")
    
    try:
        all_commits_list = []
        page = 1
        
        # Paginate through all results
        while True:
            params["page"] = page
            response = requests.get(commits_url, headers=headers, params=params)
            
            if response.status_code == 403:
                logger.error("GitHub API Rate Limit Exceeded. Please set GITHUB_TOKEN in .env")
                return []
            elif response.status_code == 404:
                logger.error(f"Repo not found (404): {repo_url}. If this is a private repo, ensure GITHUB_TOKEN is set in .env and docker-compose.yml")
                return []
            elif response.status_code != 200:
                logger.error(f"GitHub API Error: {response.status_code} - {response.text}")
                return []
                
            commits_page = response.json()
            
            # If no commits returned, we've reached the end
            if not commits_page:
                break
                
            all_commits_list.extend(commits_page)
            logger.info(f"Fetched page {page}: {len(commits_page)} commits (total so far: {len(all_commits_list)})")
            
            # If we got fewer than 100 commits, this was the last page
            if len(commits_page) < 100:
                break
                
            page += 1
        
        if not all_commits_list:
            logger.info(f"No commits found for {start_date} - {target_end}")
            return []
            
        logger.info(f"Found {len(all_commits_list)} total commits. Fetching details...")
        
        structured_commits = []
        
        # 4. Fetch details (diffs) for each commit
        for item in all_commits_list:
            sha = item['sha']
            commit_url = item['url'] # API url for specific commit
            
            # Get full commit details including files/patch
            detail_resp = requests.get(commit_url, headers=headers)
            if detail_resp.status_code != 200:
                continue
                
            detail = detail_resp.json()
            
            # Aggregate all patches in this commit AND collect file stats
            full_diff = ""
            file_stats = []
            
            for file in detail.get('files', []):
                filename = file.get('filename', 'unknown')
                patch = file.get('patch', '')
                co_authors = []
                if 'Co-authored-by:' in patch:
                    for line in patch.splitlines():
                        if line.startswith('Co-authored-by:'):
                            co_author = line.replace('Co-authored-by:', '').strip()
                            co_authors.append(co_author)
                #endfor
                # Collect stats for CSV
                file_stats.append({
                    "filename": os.path.basename(filename),
                    "filepath": filename,
                    "additions": file.get('additions', 0),
                    "deletions": file.get('deletions', 0),
                    "changes": patch,
                    'status': file.get('status', 'unknown'),
                    'author': detail['commit']['author']['name'],
                    'co-author': ', '.join(co_authors)
                })

                if patch:
                    full_diff += f"\n--- {filename} ---\n{patch}\n"
            
            # Truncate massive diffs for LLM safety
            if len(full_diff) > 15000:
                full_diff = full_diff[:15000] + "\n...[Diff truncated]..."

            structured_commits.append({
                "repo": f"{owner}/{repo}",
                "hash": sha,
                "author": detail['commit']['author']['name'],
                "timestamp": detail['commit']['author']['date'],
                "message": detail['commit']['message'],
                "diff": full_diff,
                "file_stats": file_stats
            })
            
        return structured_commits

    except Exception as e:
        logger.error(f"Error fetching from GitHub API: {e}")
        return []