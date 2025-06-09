import re
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from typing import List, Dict, Tuple, Optional
import asyncio
from dataclasses import dataclass
import json
import subprocess
from pathlib import Path
import glob
import os 
import chardet
import logging
from sklearn.feature_extraction.text import TfidfVectorizer
import openai
from openai import AsyncOpenAI
import time
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text
import requests
import base64
import urllib.parse
import asyncio
import os
from dotenv import load_dotenv

# Initialize Rich console for beautiful output
console = Console()

# Configure logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

@dataclass
class TranscriptTopic:
    keyword: str
    context: str
    description: str
    related_concepts: List[str]

@dataclass
class CodeBlock:
    file_path: str
    function_name: str
    content: str
    start_line: int
    end_line: int

@dataclass 
class CodeMatch:
    code_block: 'CodeBlock'
    topic: TranscriptTopic
    similarity_score: float
    reasoning: str

class TranscriptCodeMatcher:
    def __init__(self, openai_api_key: str):
        """Initialize with OpenAI API key"""
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words='english',
            ngram_range=(1, 2)
        )
        console.print("✅ [green bold]OpenAI client initialized successfully[/green bold]")

    async def extract_topics_from_transcript(self, transcript: str) -> List[TranscriptTopic]:
        """Extract topics from full transcript blocks using ChatGPT."""
        entries = re.split(r"\n+", transcript)
        topics = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("🔍 Extracting topics from transcript...", total=len(entries))
            
            # Process in batches to avoid API rate limits
            batch_size = 5
            for i in range(0, len(entries), batch_size):
                batch = entries[i:i+batch_size]
                batch_topics = await self._process_batch_with_chatgpt(batch)
                topics.extend(batch_topics)
                progress.advance(task, min(batch_size, len(entries) - i))
                
                # Rate limiting - wait between batches
                if i + batch_size < len(entries):
                    await asyncio.sleep(0.5)

        return topics

    async def _process_batch_with_chatgpt(self, batch: List[str]) -> List[TranscriptTopic]:
        async def safe_analyze(block: str) -> TranscriptTopic:
            keyword = block[:40] if len(block) > 40 else block
            try:
                description, concepts = await asyncio.wait_for(
                    self._analyze_topic_with_chatgpt(keyword, block), timeout=15
                )
                return TranscriptTopic(
                    keyword=keyword.strip(),
                    context=block.strip(),
                    description=description,
                    related_concepts=concepts
                )
            except Exception as e:
                return TranscriptTopic(
                    keyword=keyword.strip(),
                    context=block.strip(),
                    description=f"Programming task related to {keyword}",
                    related_concepts=self._extract_keywords_simple(block)
                )

        # Filter valid blocks
        valid_blocks = [b for b in batch if len(b.strip()) >= 20]
        
        # Launch concurrent analysis
        results = await asyncio.gather(
            *(safe_analyze(block) for block in valid_blocks),
            return_exceptions=False
        )
        
        return results

    def _extract_keywords_simple(self, text: str) -> List[str]:
        """Simple keyword extraction fallback"""
        programming_terms = re.findall(r'\b(?:function|method|class|api|data|process|system|code|implement|create|build|develop|update|fix|debug|test)\b', text.lower())
        identifiers = re.findall(r'\b[a-z][a-zA-Z0-9_]*[A-Z][a-zA-Z0-9_]*\b|\b[a-z][a-z0-9_]*_[a-z0-9_]+\b', text)
        
        return list(set(programming_terms + identifiers))[:8]
    
    async def _analyze_topic_with_chatgpt(self, keyword: str, context: str) -> Tuple[str, List[str]]:
        """Use ChatGPT to understand what programming concepts relate to a transcript topic"""
        
        prompt = f"""
        Analyze this meeting transcript excerpt and identify programming concepts:
        
        Keyword: {keyword}
        Context: {context}
        
        Please provide:
        1. A brief description of what code functionality this might require
        2. Up to 5 related programming concepts (e.g., "API development", "data processing", "user interface")
        
        Respond in JSON format:
        {{
            "description": "brief description",
            "concepts": ["concept1", "concept2", "concept3"]
        }}
        """
        
        try:
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a technical analyst helping to map meeting discussions to programming requirements. Keep responses concise and focused on actionable development tasks."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.3
            )
            
            result_text = response.choices[0].message.content.strip()
            
            try:
                result_json = json.loads(result_text)
                description = result_json.get("description", f"Code implementation for {keyword}")
                concepts = result_json.get("concepts", [])[:5]
                return description, concepts
            except json.JSONDecodeError:
                return self._parse_chatgpt_fallback(result_text, keyword)
            
        except Exception as e:
            logger.warning(f"Error analyzing topic with ChatGPT: {e}")
            return self._generate_description_heuristic(keyword, context, [])
    
    def _parse_chatgpt_fallback(self, text: str, keyword: str) -> Tuple[str, List[str]]:
        """Parse ChatGPT response when JSON parsing fails"""
        lines = text.split('\n')
        description = f"Code implementation for {keyword}"
        concepts = []
        
        for line in lines:
            if 'description' in line.lower():
                desc_match = re.search(r'[:"](.*?)[",]', line)
                if desc_match:
                    description = desc_match.group(1).strip()
            elif 'concept' in line.lower() and any(char in line for char in ['"', "'"]):
                concept_matches = re.findall(r'["\']([^"\']+)["\']', line)
                concepts.extend(concept_matches)
        
        return description, concepts[:5]
    
    def _generate_description_heuristic(self, keyword: str, context: str, concepts: List[str]) -> Tuple[str, List[str]]:
        """Generate description using heuristics instead of LLM generation"""
        
        if any(word in context.lower() for word in ['api', 'endpoint', 'request']):
            return f"API functionality related to {keyword}", ["API development", "HTTP requests", "endpoint design"]
        elif any(word in context.lower() for word in ['data', 'database', 'store']):
            return f"Data processing and storage for {keyword}", ["data processing", "database operations", "data validation"]
        elif any(word in context.lower() for word in ['ui', 'interface', 'display', 'view']):
            return f"User interface implementation for {keyword}", ["user interface", "frontend development", "UI components"]
        elif any(word in context.lower() for word in ['test', 'testing', 'verify']):
            return f"Testing and validation for {keyword}", ["testing", "validation", "quality assurance"]
        elif any(word in context.lower() for word in ['config', 'setup', 'install']):
            return f"Configuration and setup for {keyword}", ["configuration", "setup", "deployment"]
        else:
            return f"General functionality implementation for {keyword}", ["general development", "code implementation"]
    
    async def find_matching_code_blocks(self, topics: List[TranscriptTopic], 
                                      code_blocks: List['CodeBlock']) -> List[CodeMatch]:
        """Find code blocks that implement functionality mentioned in transcript topics using TF-IDF similarity"""
        
        # FIXED: Handle empty code_blocks case
        if not code_blocks:
            console.print("⚠️ [yellow]No code blocks found. Skipping similarity analysis.[/yellow]")
            return []
        
        if not topics:
            console.print("⚠️ [yellow]No topics found. Skipping similarity analysis.[/yellow]")
            return []
        
        matches = []
        
        topic_texts = [f"{topic.keyword} {topic.description} {' '.join(topic.related_concepts)}" 
                      for topic in topics]
        code_texts = [f"{cb.function_name} {cb.content[:500]}" for cb in code_blocks]
        
        all_texts = topic_texts + code_texts
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("🔍 Computing TF-IDF vectors for semantic matching...", total=1)
            tfidf_matrix = self.tfidf_vectorizer.fit_transform(all_texts)
            progress.advance(task, 1)
        
        topic_matrix = tfidf_matrix[:len(topic_texts)]
        code_matrix = tfidf_matrix[len(topic_texts):]
        
        similarities = cosine_similarity(topic_matrix, code_matrix)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("🤖 Finding semantic matches...", total=len(topics))
            
            for i, topic in enumerate(topics):
                topic_similarities = similarities[i]
                
                for j, similarity_score in enumerate(topic_similarities):
                    if similarity_score > 0.3:
                        reasoning = await self._generate_match_reasoning_with_chatgpt(
                            topic, code_blocks[j], similarity_score
                        )
                        
                        matches.append(CodeMatch(
                            code_block=code_blocks[j],
                            topic=topic,
                            similarity_score=float(similarity_score),
                            reasoning=reasoning
                        ))
                
                progress.advance(task, 1)
        
        return sorted(matches, key=lambda x: x.similarity_score, reverse=True)
    
    async def _generate_match_reasoning_with_chatgpt(self, topic: TranscriptTopic, 
                                                   code_block: CodeBlock, score: float) -> str:
        """Generate reasoning for why a topic matches a code block using ChatGPT"""
        
        if score < 0.5:
            return self._generate_match_reasoning_heuristic(topic, code_block, score)
        
        prompt = f"""
        Explain why this meeting topic matches this code function:
        
        Meeting Topic: {topic.keyword}
        Topic Description: {topic.description}
        Related Concepts: {', '.join(topic.related_concepts)}
        
        Function Name: {code_block.function_name}
        Code Preview: {code_block.content[:200]}
        
        Similarity Score: {score:.2f}
        
        Provide a brief explanation (1-2 sentences) of why they match.
        """
        
        try:
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are analyzing code-to-requirements matches. Be concise and technical."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=100,
                temperature=0.2
            )
            
            reasoning = response.choices[0].message.content.strip()
            return reasoning
            
        except Exception as e:
            logger.warning(f"Error generating reasoning with ChatGPT: {e}")
            return self._generate_match_reasoning_heuristic(topic, code_block, score)
    
    def _generate_match_reasoning_heuristic(self, topic: TranscriptTopic, code_block: CodeBlock, score: float) -> str:
        """Generate reasoning for why a topic matches a code block using heuristics"""
        
        function_name_words = re.findall(r'[A-Z][a-z]*|[a-z]+', code_block.function_name.replace('_', ' '))
        topic_words = topic.keyword.lower().split()
        
        common_words = set(word.lower() for word in function_name_words) & set(topic_words)
        
        if common_words:
            return f"Function name '{code_block.function_name}' contains keywords {list(common_words)} matching topic '{topic.keyword}'. Semantic similarity: {score:.2f}"
        
        code_content_lower = code_block.content.lower()
        matching_concepts = [concept for concept in topic.related_concepts 
                           if any(word in code_content_lower for word in concept.lower().split())]
        
        if matching_concepts:
            return f"Code implements concepts: {matching_concepts}. Semantic similarity: {score:.2f}"
        
        return f"High semantic similarity ({score:.2f}) between topic '{topic.keyword}' and function '{code_block.function_name}'"
    
    def generate_beautiful_report(self, matches: List[CodeMatch]) -> str:
        """Generate a beautiful, appealing report and save to file"""
        
        # Handle empty matches case
        if not matches:
            console.print("\n")
            console.print(Panel.fit(
                "[bold yellow]⚠️ No code matches found[/bold yellow]\n"
                "[dim]This could be due to GitHub rate limits or no semantic matches above threshold.[/dim]",
                border_style="yellow"
            ))
            return "No matches found"
        
        # Group matches by topic
        by_topic = {}
        for match in matches:
            topic_key = match.topic.keyword
            if topic_key not in by_topic:
                by_topic[topic_key] = []
            by_topic[topic_key].append(match)
        
        # Display header
        console.print("\n")
        console.print(Panel.fit(
            "[bold cyan]🎯 Meeting Topics → Code Implementation Analysis[/bold cyan]\n"
            f"[dim]Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}[/dim]",
            border_style="cyan"
        ))
        
        # Summary statistics
        stats_table = Table(show_header=False, box=None, padding=(0, 2))
        stats_table.add_column(style="bold blue")
        stats_table.add_column(style="green")
        
        stats_table.add_row("📊 Topics Analyzed:", str(len(by_topic)))
        stats_table.add_row("💻 Code Matches Found:", str(len(matches)))
        stats_table.add_row("🎯 Average Match Score:", f"{sum(m.similarity_score for m in matches) / len(matches):.2f}" if matches else "N/A")
        
        console.print(Panel(stats_table, title="[bold]Summary Statistics[/bold]", border_style="green"))
        
        # Generate file report content
        report_content = []
        report_content.append("# 🎯 Meeting Topics → Code Implementation Analysis")
        report_content.append(f"Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
        report_content.append("\n## 📊 Summary Statistics")
        report_content.append(f"- **Topics Analyzed:** {len(by_topic)}")
        report_content.append(f"- **Code Matches Found:** {len(matches)}")
        report_content.append(f"- **Average Match Score:** {sum(m.similarity_score for m in matches) / len(matches):.2f}" if matches else "N/A")
        report_content.append("\n---\n")
        
        # Display matches by topic
        for topic_keyword, topic_matches in by_topic.items():
            if not topic_matches:
                continue
                
            topic = topic_matches[0].topic
            
            # Console output
            console.print(f"\n[bold magenta]🎯 {topic_keyword}[/bold magenta]")
            console.print(f"[dim]{topic.context[:100]}...[/dim]")
            
            # File output
            report_content.append(f"## 🎯 {topic_keyword}")
            report_content.append(f"**Context:** {topic.context}")
            report_content.append(f"**Description:** {topic.description}")
            report_content.append(f"**Related Concepts:** {', '.join(topic.related_concepts)}")
            report_content.append(f"\n**Code Matches Found:** {len(topic_matches)}")
            report_content.append("")
            
            # Create table for matches
            matches_table = Table(show_header=True, header_style="bold cyan")
            matches_table.add_column("Function", style="green", width=25)
            matches_table.add_column("File", style="blue", width=30)
            matches_table.add_column("Score", justify="center", style="yellow", width=8)
            matches_table.add_column("Reasoning", style="white", width=50)
            
            for i, match in enumerate(sorted(topic_matches, key=lambda x: x.similarity_score, reverse=True)[:5], 1):
                score_color = "red" if match.similarity_score < 0.4 else "yellow" if match.similarity_score < 0.7 else "green"
                matches_table.add_row(
                    f"`{match.code_block.function_name}`",
                    f"`{match.code_block.file_path}`",
                    f"[{score_color}]{match.similarity_score:.2f}[/{score_color}]",
                    match.reasoning[:80] + "..." if len(match.reasoning) > 80 else match.reasoning
                )
                
                # Add to file report
                report_content.append(f"### {i}. `{match.code_block.function_name}` (Score: {match.similarity_score:.2f})")
                report_content.append(f"**File:** `{match.code_block.file_path}`")
                report_content.append(f"**Lines:** {match.code_block.start_line}-{match.code_block.end_line}")
                report_content.append(f"**Reasoning:** {match.reasoning}")
                report_content.append(f"**Code Preview:**")
                report_content.append(f"```python")
                report_content.append(match.code_block.content[:300] + "..." if len(match.code_block.content) > 300 else match.code_block.content)
                report_content.append(f"```")
                report_content.append("")
            
            console.print(matches_table)
            report_content.append("---\n")
        
        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"meeting_code_analysis_{timestamp}.md"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write('\n'.join(report_content))
            
            console.print(f"\n✅ [green bold]Report saved to: {filename}[/green bold]")
            return filename
            
        except Exception as e:
            console.print(f"\n❌ [red]Error saving report: {e}[/red]")
            return "Error saving report"

class GitHubCodeExtractor:
    """Extract code from GitHub repositories using GitHub API with improved rate limiting"""
    
    def __init__(self, github_token: Optional[str] = None):
        self.github_token = github_token
        self.session = requests.Session()
        
        if github_token:
            self.session.headers.update({
                'Authorization': f'token {github_token}',
                'Accept': 'application/vnd.github.v3+json'
            })
        
        # Enhanced rate limiting
        self.requests_count = 0
        self.last_request_time = time.time()
        self.rate_limit_remaining = 5000  # Default for authenticated
        self.rate_limit_reset = time.time() + 3600
    
    def _rate_limit(self):
        """Enhanced rate limiting to avoid hitting GitHub API limits"""
        self.requests_count += 1
        current_time = time.time()
        
        # Check if we're close to rate limit
        if self.rate_limit_remaining < 10:
            wait_time = max(0, self.rate_limit_reset - current_time)
            if wait_time > 0:
                console.print(f"⏳ [yellow]Rate limit reached. Waiting {wait_time:.0f} seconds...[/yellow]")
                time.sleep(min(wait_time, 300))  # Max 5 minutes wait
        
        # Standard rate limiting
        if self.requests_count > 30 and (current_time - self.last_request_time) < 60:
            time.sleep(2)
        
        self.last_request_time = current_time
    
    def _update_rate_limit_info(self, response):
        """Update rate limit info from response headers"""
        if 'X-RateLimit-Remaining' in response.headers:
            self.rate_limit_remaining = int(response.headers['X-RateLimit-Remaining'])
        if 'X-RateLimit-Reset' in response.headers:
            self.rate_limit_reset = int(response.headers['X-RateLimit-Reset'])
    
    def _parse_github_url(self, repo_url: str) -> Tuple[str, str]:
        """Parse GitHub URL to extract owner and repo name"""
        # Handle different GitHub URL formats
        patterns = [
            r'github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$',
            r'github\.com/([^/]+)/([^/]+)/tree/([^/]+)',
            r'github\.com/([^/]+)/([^/]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, repo_url)
            if match:
                owner, repo = match.group(1), match.group(2)
                # Remove .git suffix if present
                repo = repo.replace('.git', '')
                return owner, repo
        
        raise ValueError(f"Invalid GitHub URL format: {repo_url}")
    
    def _get_repo_contents(self, owner: str, repo: str, path: str = "") -> List[Dict]:
        """Get repository contents from GitHub API with error handling"""
        self._rate_limit()
        
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        print(f"[DEBUG] GitHub API request: https://api.github.com/repos/{owner}/{repo}/contents/{path}")
        print(f"[DEBUG] Authorization header: {self.session.headers.get('Authorization')}")
        try:
            response = self.session.get(url, timeout=30)
            self._update_rate_limit_info(response)
            
            if response.status_code == 403:
                logger.warning(f"Rate limit exceeded for {url}")
                return []
            elif response.status_code == 404:
                logger.warning(f"Path not found: {path}")
                return []
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching repo contents: {e}")
            return []
    
    def _get_file_content(self, owner: str, repo: str, file_path: str) -> Optional[str]:
        """Get file content from GitHub API with error handling"""
        self._rate_limit()
        
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
        
        try:
            response = self.session.get(url, timeout=30)
            self._update_rate_limit_info(response)
            
            if response.status_code == 403:
                logger.warning(f"Rate limit exceeded for file {file_path}")
                return None
            elif response.status_code == 404:
                logger.warning(f"File not found: {file_path}")
                return None
            
            response.raise_for_status()
            file_data = response.json()
            
            if file_data.get('encoding') == 'base64':
                try:
                    content = base64.b64decode(file_data['content']).decode('utf-8')
                    return content
                except UnicodeDecodeError:
                    logger.warning(f"Could not decode file {file_path}")
                    return None
            else:
                return file_data.get('content', '')
                
        except Exception as e:
            logger.warning(f"Error fetching file {file_path}: {e}")
            return None
    
    def _find_supported_files(self, owner: str, repo: str, path: str = "", max_depth: int = 3) -> List[str]:
        """Recursively find all supported source files in the repository with depth limit"""
        if max_depth <= 0:
            return []
            
        supported_exts = ('.py', '.ts', '.tsx', '.js')
        matched_files = []
        contents = self._get_repo_contents(owner, repo, path)
        
        for item in contents:
            if item['type'] == 'file' and item['name'].endswith(supported_exts):
                matched_files.append(item['path'])
            elif item['type'] == 'dir' and not item['name'].startswith('.'):
                subdir_files = self._find_supported_files(owner, repo, item['path'], max_depth - 1)
                matched_files.extend(subdir_files)
        
        return matched_files
    
    def _find_function_end(self, code_from_def: str) -> int:
        """Find the end of a function definition"""
        lines = code_from_def.split('\n')
        if not lines:
            return len(code_from_def)
        
        # Get the indentation of the def line
        def_line = lines[0]
        def_indent = len(def_line) - len(def_line.lstrip())
        
        # Find the end of the function
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "":
                continue
            
            line_indent = len(line) - len(line.lstrip())
            
            # If we find a line with same or less indentation than def, function ends
            if line_indent <= def_indent and line.strip():
                return sum(len(l) + 1 for l in lines[:i])
        
        return len(code_from_def)
    
    async def scan_github_repository(self, repo_url: str) -> List[CodeBlock]:
        """Scan GitHub repository for functions and methods with fallback strategies"""
        try:
            owner, repo = self._parse_github_url(repo_url)
            console.print(f"🔍 [blue]Scanning GitHub repository: {owner}/{repo}[/blue]")
            
            # First check rate limits
            if self.rate_limit_remaining < 10:
                console.print("⚠️ [yellow]GitHub rate limit too low. Consider using a GitHub token or waiting.[/yellow]")
            
            supported_files = self._find_supported_files(owner, repo, max_depth=5)
            console.print(f"📁 [green]Found {len(supported_files)} supported files[/green]")
            
            if not supported_files:
                console.print("⚠️ [yellow]No supported files found in repository[/yellow]")
                return []
            
            code_blocks = []
            processed_files = 0
            max_files = min(20, len(supported_files))  # Limit to first 20 files
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(f"📥 Downloading and analyzing files...", total=max_files)
                
                for file_path in supported_files[:max_files]:
                    try:
                        content = self._get_file_content(owner, repo, file_path)
                        if content is None:
                            progress.advance(task, 1)
                            continue
                        
                        # Extract functions from the file content
                        if file_path.endswith('.py'):
                            function_matches = list(re.finditer(r"def\s+(\w+)\s*\(", content))
                        elif file_path.endswith(('.ts', '.tsx', '.js')):
                            function_matches = list(re.finditer(
                                r"(?:function\s+(\w+)\s*\(|const\s+(\w+)\s*=\s*\(|(\w+)\s*:\s*\([^)]+\)\s*=>)",
                                content
                            ))
                        else:
                            function_matches = []
                        
                        for match in function_matches:
                            func_name = match.group(1) or match.group(2) or match.group(3) or "anonymous"
                            start_pos = match.start()
                            lines = content[:start_pos].count("\n") + 1
                            end_pos = self._find_function_end(content[start_pos:])
                            
                            code_blocks.append(CodeBlock(
                                file_path=file_path,
                                function_name=func_name,
                                content=content[start_pos:start_pos + end_pos],
                                start_line=lines,
                                end_line=lines + content[start_pos:start_pos + end_pos].count("\n")
                            ))
                        
                        processed_files += 1
                            
                    except Exception as e:
                        logger.warning(f"Error processing file {file_path}: {e}")
                        continue
                    
                    progress.advance(task, 1)
                
            console.print(f"✅ [green]Successfully processed {processed_files} files and found {len(code_blocks)} functions[/green]")
            return code_blocks
            
        except Exception as e:
            console.print(f"❌ [red]Error scanning GitHub repository: {e}[/red]")
            return []

class LocalCodeExtractor:
    """Extract code from local directory with improved file handling"""
    
    def __init__(self, directory: str):
        self.directory = Path(directory)
        if not self.directory.exists():
            raise ValueError(f"Directory {directory} does not exist")
    
    def _detect_encoding(self, file_path: Path) -> str:
        """Detect file encoding using chardet"""
        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read(10000)  # Read first 10KB
                result = chardet.detect(raw_data)
                return result.get('encoding', 'utf-8') or 'utf-8'
        except Exception:
            return 'utf-8'
    
    def _read_file_safely(self, file_path: Path) -> Optional[str]:
        """Safely read file with encoding detection"""
        encoding = self._detect_encoding(file_path)
        
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            # Try alternative encodings
            for alt_encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    with open(file_path, 'r', encoding=alt_encoding) as f:
                        return f.read()
                except UnicodeDecodeError:
                    continue
        except Exception as e:
            logger.warning(f"Error reading file {file_path}: {e}")
        
        return None
    
    def _extract_python_functions(self, content: str, file_path: str) -> List[CodeBlock]:
        """Extract Python functions from content"""
        functions = []
        
        # Find all function definitions
        function_matches = list(re.finditer(r"def\s+(\w+)\s*\(", content))
        
        for match in function_matches:
            func_name = match.group(1)
            start_pos = match.start()
            start_line = content[:start_pos].count("\n") + 1
            
            # Find function end
            lines = content[start_pos:].split('\n')
            if not lines:
                continue
                
            def_indent = len(lines[0]) - len(lines[0].lstrip())
            end_line_offset = 0
            
            for i, line in enumerate(lines[1:], 1):
                if line.strip() == "":
                    continue
                    
                line_indent = len(line) - len(line.lstrip())
                if line_indent <= def_indent and line.strip():
                    end_line_offset = i
                    break
            else:
                end_line_offset = len(lines)
            
            func_content = '\n'.join(lines[:end_line_offset])
            end_line = start_line + end_line_offset - 1
            
            functions.append(CodeBlock(
                file_path=file_path,
                function_name=func_name,
                content=func_content,
                start_line=start_line,
                end_line=end_line
            ))
        
        return functions
    
    def _extract_js_functions(self, content: str, file_path: str) -> List[CodeBlock]:
        """Extract JavaScript/TypeScript functions from content"""
        functions = []
        
        # Multiple patterns for JS/TS functions
        patterns = [
            r"function\s+(\w+)\s*\(",
            r"const\s+(\w+)\s*=\s*\(",
            r"(\w+)\s*:\s*\([^)]*\)\s*=>",
            r"(\w+)\s*=\s*\([^)]*\)\s*=>",
        ]
        
        for pattern in patterns:
            matches = list(re.finditer(pattern, content))
            
            for match in matches:
                func_name = match.group(1)
                start_pos = match.start()
                start_line = content[:start_pos].count("\n") + 1
                
                # Simple function extraction - find next function or end of file
                remaining_content = content[start_pos:]
                next_func_match = None
                
                for p in patterns:
                    next_match = re.search(p, remaining_content[100:])  # Skip current function
                    if next_match and (next_func_match is None or next_match.start() < next_func_match.start()):
                        next_func_match = next_match
                
                if next_func_match:
                    func_content = remaining_content[:100 + next_func_match.start()]
                else:
                    func_content = remaining_content[:1000]  # Take first 1000 chars
                
                end_line = start_line + func_content.count('\n')
                
                functions.append(CodeBlock(
                    file_path=file_path,
                    function_name=func_name,
                    content=func_content,
                    start_line=start_line,
                    end_line=end_line
                ))
        
        return functions
    
    async def scan_local_directory(self) -> List[CodeBlock]:
        """Scan local directory for code functions"""
        console.print(f"🔍 [blue]Scanning local directory: {self.directory}[/blue]")
        
        supported_extensions = {'.py', '.js', '.ts', '.tsx'}
        code_blocks = []
        
        # Find all supported files
        all_files = []
        for ext in supported_extensions:
            pattern = f"**/*{ext}"
            files = list(self.directory.glob(pattern))
            all_files.extend(files)
        
        # Filter out common non-source directories
        exclude_dirs = {'node_modules', '.git', '__pycache__', '.venv', 'venv', 'build', 'dist'}
        filtered_files = []
        
        for file_path in all_files:
            if not any(excluded in file_path.parts for excluded in exclude_dirs):
                filtered_files.append(file_path)
        
        console.print(f"📁 [green]Found {len(filtered_files)} supported files[/green]")
        
        if not filtered_files:
            console.print("⚠️ [yellow]No supported files found in directory[/yellow]")
            return []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("📥 Processing local files...", total=len(filtered_files))
            
            for file_path in filtered_files:
                try:
                    content = self._read_file_safely(file_path)
                    if content is None:
                        progress.advance(task, 1)
                        continue
                    
                    relative_path = str(file_path.relative_to(self.directory))
                    
                    if file_path.suffix == '.py':
                        functions = self._extract_python_functions(content, relative_path)
                    elif file_path.suffix in ['.js', '.ts', '.tsx']:
                        functions = self._extract_js_functions(content, relative_path)
                    else:
                        functions = []
                    
                    code_blocks.extend(functions)
                    
                except Exception as e:
                    logger.warning(f"Error processing file {file_path}: {e}")
                
                progress.advance(task, 1)
        
        console.print(f"✅ [green]Successfully found {len(code_blocks)} functions[/green]")
        return code_blocks

async def main():
    """Main function to run the transcript-to-code matching analysis"""
    
    # Load environment variables
    load_dotenv()
    
    console.print(Panel.fit(
        "[bold cyan]🎯 Meeting Transcript → Code Implementation Matcher[/bold cyan]\n"
        "[dim]Analyze meeting transcripts and find related code implementations[/dim]",
        border_style="cyan"
    ))
    
    # Get OpenAI API key
    openai_api_key = os.getenv('OPENAI_API_KEY')
    if not openai_api_key:
        console.print("❌ [red]OPENAI_API_KEY not found in environment variables[/red]")
        console.print("Please set your OpenAI API key in a .env file or environment variable")
        return
    
    # Get GitHub token (optional)
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        console.print("⚠️ [yellow]GITHUB_TOKEN not found. GitHub API calls will be rate-limited.[/yellow]")
    
    # Initialize the matcher
    try:
        matcher = TranscriptCodeMatcher(openai_api_key)
    except Exception as e:
        console.print(f"❌ [red]Error initializing matcher: {e}[/red]")
        return
    
    # Get transcript input
    console.print("\n[bold]📝 Transcript Input[/bold]")
    transcript_choice = console.input("Enter transcript text directly or provide file path: ").strip()
    
    transcript_text = ""
    if os.path.isfile(transcript_choice):
        try:
            with open(transcript_choice, 'r', encoding='utf-8') as f:
                transcript_text = f.read()
            console.print(f"✅ [green]Loaded transcript from file: {transcript_choice}[/green]")
        except Exception as e:
            console.print(f"❌ [red]Error reading transcript file: {e}[/red]")
            return
    else:
        transcript_text = transcript_choice
        console.print("✅ [green]Using provided transcript text[/green]")
    
    if not transcript_text.strip():
        console.print("❌ [red]No transcript text provided[/red]")
        return
    
    # Get code source
    console.print("\n[bold]💻 Code Source[/bold]")
    console.print("Choose code source:")
    console.print("1. GitHub repository URL")
    console.print("2. Local directory path")
    
    source_choice = console.input("Enter choice (1 or 2): ").strip()
    
    code_blocks = []
    
    if source_choice == "1":
        repo_url = console.input("Enter GitHub repository URL: ").strip()
        if not repo_url:
            console.print("❌ [red]No repository URL provided[/red]")
            return
        
        try:
            extractor = GitHubCodeExtractor(github_token)
            code_blocks = await extractor.scan_github_repository(repo_url)
        except Exception as e:
            console.print(f"❌ [red]Error scanning GitHub repository: {e}[/red]")
            return
    
    elif source_choice == "2":
        dir_path = console.input("Enter local directory path: ").strip()
        if not dir_path:
            console.print("❌ [red]No directory path provided[/red]")
            return
        
        try:
            extractor = LocalCodeExtractor(dir_path)
            code_blocks = await extractor.scan_local_directory()
        except Exception as e:
            console.print(f"❌ [red]Error scanning local directory: {e}[/red]")
            return
    
    else:
        console.print("❌ [red]Invalid choice[/red]")
        return
    
    if not code_blocks:
        console.print("❌ [red]No code blocks found to analyze[/red]")
        return
    
    # Extract topics from transcript
    console.print("\n[bold]🔍 Analysis Phase[/bold]")
    try:
        topics = await matcher.extract_topics_from_transcript(transcript_text)
        console.print(f"✅ [green]Extracted {len(topics)} topics from transcript[/green]")
    except Exception as e:
        console.print(f"❌ [red]Error extracting topics: {e}[/red]")
        return
    
    # Find matching code blocks
    try:
        matches = await matcher.find_matching_code_blocks(topics, code_blocks)
        console.print(f"✅ [green]Found {len(matches)} code matches[/green]")
    except Exception as e:
        console.print(f"❌ [red]Error finding matches: {e}[/red]")
        return
    
    # Generate and display report
    console.print("\n[bold]📊 Generating Report[/bold]")
    try:
        report_file = matcher.generate_beautiful_report(matches)
        console.print(f"✅ [green]Analysis complete! Report saved as: {report_file}[/green]")
    except Exception as e:
        console.print(f"❌ [red]Error generating report: {e}[/red]")
        return

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n❌ [red]Analysis interrupted by user[/red]")
    except Exception as e:
        console.print(f"\n❌ [red]Unexpected error: {e}[/red]")
        logger.exception("Unexpected error in main")


