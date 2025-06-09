import requests 
import os 
from dotenv import load_dotenv
from collections import defaultdict
import json
from datetime import datetime, timedelta

load_dotenv()

# Configuration
GITHUB_TOKEN = os.getenv("GITHUB_PAT")
if not GITHUB_TOKEN:
    raise ValueError("❌ GITHUB_PAT is not set in environment or .env file.")

HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}
REPO = "KellisLab/auto-meeting-minutes"
BASE_URL = f"https://api.github.com/repos/{REPO}"

# Author role mapping (update as needed)
AUTHOR_ROLES = {
    "Alice": "frontend",
    "Bob": "backend", 
    "Charlie": "infra"
}

def get_commits(repo=None, per_page=30, max_pages=5):
    """Fetch commits from the repository"""
    if repo:
        base_url = f"https://api.github.com/repos/{repo}"
    else:
        base_url = BASE_URL
        
    commits = []
    for page in range(1, max_pages + 1):
        url = f"{base_url}/commits?per_page={per_page}&page={page}"
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            print(f"Failed to fetch commits (page {page}):", response.text)
            break
        page_commits = response.json()
        if not page_commits:  # No more commits
            break
        commits.extend(page_commits)
    return commits

def categorize_file(filename):
    """Categorize files by type"""
    if filename.endswith((".ts", ".tsx", ".js", ".jsx")):
        return "frontend"
    elif filename.endswith((".py", ".java", ".go", ".rb")):
        return "backend"
    elif filename.endswith(("_test.py", "test.js")) or "test" in filename.lower():
        return "tests"
    elif filename.startswith((".github/", "Dockerfile", "Makefile")) or filename in ["Dockerfile", "Makefile"]:
        return "infra"
    else:
        return "misc"

def analyze_commits(commits):
    """Analyze commits to build file-author mappings"""
    file_author_map = defaultdict(set)
    author_files_map = defaultdict(set)

    for commit in commits:
        sha = commit["sha"]
        author = commit["commit"]["author"]["name"]
        
        # Fetch full commit data to get files
        commit_url = f"{BASE_URL}/commits/{sha}"
        try:
            commit_detail = requests.get(commit_url, headers=HEADERS).json()
            files = commit_detail.get("files", [])
            
            for file in files:
                filename = file["filename"]
                file_author_map[filename].add(author)
                author_files_map[author].add(filename)
        except Exception as e:
            print(f"Error fetching commit {sha}: {e}")
            continue

    return file_author_map, author_files_map

def get_commit_file_map(commits):
    """Build a map of author -> file -> commit count"""
    file_map = defaultdict(lambda: defaultdict(int))
    
    for commit in commits:
        sha = commit["sha"]
        author = commit["commit"]["author"]["name"]
        
        try:
            detail = requests.get(commit["url"], headers=HEADERS).json()
            for file in detail.get("files", []):
                path = file["filename"]
                file_map[author][path] += 1
        except Exception as e:
            print(f"Error processing commit {sha}: {e}")
            continue
            
    return file_map

def get_contribution_heatmap(commits):
    """Get heatmap of lines changed per author per file"""
    heatmap = defaultdict(lambda: defaultdict(int))
    
    for commit in commits:
        sha = commit["sha"]
        author = commit["commit"]["author"]["name"]
        
        try:
            detail = requests.get(commit["url"], headers=HEADERS).json()
            for file in detail.get("files", []):
                lines_changed = file.get("changes", 0)
                heatmap[author][file["filename"]] += lines_changed
        except Exception as e:
            print(f"Error processing commit {sha}: {e}")
            continue
            
    return heatmap

def detect_conflicts(heatmap, threshold=0.3):
    """Detect potential conflicts based on contribution patterns"""
    file_totals = defaultdict(int)
    for author_data in heatmap.values():
        for file, lines in author_data.items():
            file_totals[file] += lines

    conflicts = defaultdict(list)
    for author, files in heatmap.items():
        for file, lines in files.items():
            if file_totals[file] > 0 and (lines / file_totals[file]) > threshold:
                conflicts[author].append(file)
    return conflicts

def filter_recent_commits(commits, days=14):
    """Filter commits to only recent ones"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    recent_commits = []
    
    for commit in commits:
        try:
            commit_date = datetime.strptime(commit["commit"]["author"]["date"], "%Y-%m-%dT%H:%M:%SZ")
            if commit_date > cutoff:
                recent_commits.append(commit)
        except Exception as e:
            print(f"Error parsing date for commit: {e}")
            continue
            
    return recent_commits

def compute_overlap(file_map):
    """Compute collaboration overlaps between authors"""
    file_to_authors = defaultdict(set)
    for author, files in file_map.items():
        for f in files:
            file_to_authors[f].add(author)
    
    overlaps = defaultdict(lambda: {"collaborate_with": set(), "coordinate_with": set()})
    for authors in file_to_authors.values():
        if len(authors) > 1:  # Only consider files with multiple authors
            for a1 in authors:
                for a2 in authors:
                    if a1 != a2:
                        overlaps[a1]["collaborate_with"].add(a2)
                        overlaps[a2]["coordinate_with"].add(a1)
    
    # Convert sets to lists for JSON serialization
    return {k: {"collaborate_with": list(v["collaborate_with"]),
                "coordinate_with": list(v["coordinate_with"])}
            for k, v in overlaps.items()}

def role_based_collaboration(overlaps, author_roles):
    """Categorize collaborations by role"""
    categorized = {}
    for author, data in overlaps.items():
        role = author_roles.get(author, "unknown")
        same_role = [a for a in data["collaborate_with"] if author_roles.get(a) == role]
        cross_role = [a for a in data["collaborate_with"] if author_roles.get(a) != role and author_roles.get(a) != "unknown"]
        
        categorized[author] = {
            "role": role,
            "same_role": same_role,
            "cross_role": cross_role
        }
    return categorized

def summarize_recommendations(name, overlap):
    """Generate human-readable summary"""
    same = overlap.get("same_role", [])
    cross = overlap.get("cross_role", [])
    
    summary = ""
    if same:
        summary += f"{name} is collaborating with peers in the same domain: {', '.join(same)}."
    if cross:
        if summary:
            summary += " "
        summary += f"Also coordinates with cross-functional contributors: {', '.join(cross)}."
    
    return summary if summary else f"{name} is working independently."

def print_insights(file_author_map, author_files_map, commits):
    """Print analysis insights"""
    print("🔍 Who edited what:\n")
    for author, files in author_files_map.items():
        print(f"{author} ➤ {sorted(list(files))}")

    print("\n⚠️  Files with multiple editors (potential conflicts):\n")
    for file, authors in file_author_map.items():
        if len(authors) > 1:
            print(f"{file}: edited by {', '.join(authors)}")
    
    # File commit frequency analysis
    file_commit_count = defaultdict(int)
    for commit in commits:
        try:
            details = requests.get(commit["url"], headers=HEADERS).json()
            for file in details.get("files", []):
                file_commit_count[file["filename"]] += 1
        except Exception as e:
            print(f"Error analyzing commit frequency: {e}")
            continue

    print("\n📊 Most frequently modified files:\n")
    sorted_files = sorted(file_commit_count.items(), key=lambda x: x[1], reverse=True)
    for f, count in sorted_files[:10]:  # Top 10
        print(f"{f}: {count} commits")

def generate_collaboration_recommendations(commits, repo_name=None):
    """Main function to generate collaboration recommendations"""
    print(f"🚀 Analyzing repository: {repo_name or REPO}")
    
    # Basic analysis
    file_author_map, author_files_map = analyze_commits(commits)
    print_insights(file_author_map, author_files_map, commits)
    
    # Advanced analysis
    file_map = get_commit_file_map(commits)
    overlaps = compute_overlap(file_map)
    
    # Role-based analysis
    role_analysis = role_based_collaboration(overlaps, AUTHOR_ROLES)
    
    print("\n🤝 Collaboration Recommendations:\n")
    for author, data in role_analysis.items():
        summary = summarize_recommendations(author, data)
        print(f"• {summary}")
    
    # Conflict detection
    heatmap = get_contribution_heatmap(commits)
    conflicts = detect_conflicts(heatmap)
    
    print("\n🚨 Potential Conflict Areas:\n")
    for author, files in conflicts.items():
        if files:
            print(f"{author} has significant contributions to: {', '.join(files[:5])}{'...' if len(files) > 5 else ''}")
    
    return overlaps

def main():
    """Main execution function"""
    try:
        # Fetch commits
        commits = get_commits()
        print(f"📈 Fetched {len(commits)} commits")
        
        # Generate recommendations
        recommendations = generate_collaboration_recommendations(commits)
        
        # Save to file
        output_file = "github_collaboration_recommendations.json"
        with open(output_file, "w") as f:
            json.dump(recommendations, f, indent=2)
        
        print(f"\n💾 Recommendations saved to {output_file}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()