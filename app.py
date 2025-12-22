from flask import Flask, render_template, request, jsonify, send_file
import os
import uuid
import threading
import time
import sys
import logging
import shutil
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
# from authlib.integrations.flask_client import OAuth  # <--- COMMENTED OUT
import requests
import json
import csv
import git_summarizer
from utils import sanitize_filename

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("AUTH_SECRET", os.urandom(24)) # Use AUTH_SECRET from env if available
app.config['UPLOAD_FOLDER'] = 'temp_files'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size

# --- OAuth Configuration ---
# oauth = OAuth(app)  # <--- COMMENTED OUT

# Register Google
# oauth.register(
#     name='google',
#     client_id=os.getenv("GOOGLE_OAUTH_ID"),
#     client_secret=os.getenv("GOOGLE_OAUTH_SECRET"),
#     server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
#     client_kwargs={'scope': 'openid email profile'}
# )

# Register GitHub
# oauth.register(
#     name='github',
#     client_id=os.getenv("GITHUB_OAUTH_ID"),
#     client_secret=os.getenv("GITHUB_OAUTH_SECRET"),
#     access_token_url='https://github.com/login/oauth/access_token',
#     access_token_params=None,
#     authorize_url='https://github.com/login/oauth/authorize',
#     authorize_params=None,
#     api_base_url='https://api.github.com/',
#     client_kwargs={'scope': 'user:email'},
# )

# Ensure temp directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Keep track of active processing jobs
processing_jobs = {}

# Import pipeline modules from current directory
try:
    import url2id
    import url2meeting_name
    import url2file
    import vtt2txt
    import txt2xlsx
    import xlsx2html
    import html_bold_converter
    import git_ops
except ImportError as e:
    logger.error(f"Error importing pipeline modules: {e}")
    sys.exit(1)

class ProcessingStatus:
    """Class to track processing status and messages"""
    def __init__(self):
        self.status = "initializing"
        self.progress = 0
        self.messages = []
        self.output_files = {}
        self.error = None
    
    def update(self, status, message, progress=None):
        self.status = status
        self.messages.append({"time": time.strftime("%H:%M:%S"), "message": message})
        if progress is not None:
            self.progress = progress
    
    def add_output_file(self, file_type, file_path):
        self.output_files[file_type] = file_path
    
    def set_error(self, error_message):
        self.status = "error"
        self.error = error_message
        self.messages.append({"time": time.strftime("%H:%M:%S"), "message": f"Error: {error_message}"})
    
    def to_dict(self):
        return {
            "status": self.status,
            "progress": self.progress,
            "messages": self.messages,
            "output_files": {k: os.path.basename(v) for k, v in self.output_files.items()},
            "error": self.error
        }

def process_url(job_id, url, options):
    """Process a URL through the pipeline"""
    status = processing_jobs[job_id]
    
    try:
        # Create job directory
        job_dir = os.path.join(app.config['UPLOAD_FOLDER'], job_id)
        os.makedirs(job_dir, exist_ok=True)
        
        # Change to job directory
        original_dir = os.getcwd()
        os.chdir(job_dir)
        
        status.update("extracting", "Extracting video ID from URL...", 5)
        # 0. Extract video ID
        video_id = url2id.extract_id_from_url(url)
        if not video_id:
            status.set_error("Could not extract a valid video ID from the URL")
            os.chdir(original_dir)
            return
        status.update("extracting_name", "Extracting meeting name from URL...", 10)
        
        # 1. Extract meeting name
        meeting_name = url2meeting_name.get_meeting_name_from_viewer_page(url)# remember it might be None // we will have LLM figure it out later
        file_prefix = sanitize_filename(meeting_name) if meeting_name else video_id
        status.update("name_extracted", f"Extracted meeting name: {meeting_name}", 10)
        
        
        # 2. Download transcript
        srt_file = f"{file_prefix}.srt"
        language = options.get("language", "English_USA")
        
        if not url2file.download_transcript(video_id, srt_file, language):
            status.set_error("Failed to download transcript")
            os.chdir(original_dir)
            return
        status.update("downloading", "Downloaded transcript...", 15)
        
        # 3. Convert SRT to TXT
        txt_file = f"{file_prefix}.txt"
        txt_file = vtt2txt.vtt_to_txt(srt_file, txt_file)
        status.update("converting", "Converted SRT to TXT...", 20)
        
        # 4. Convert TXT to XLSX
        xlsx_file = f"{file_prefix}.xlsx"
        xlsx_file = txt2xlsx.txt_to_xlsx(txt_file, xlsx_file)
        status.update("excel", "Converted TXT to Excel format...", 25)

        # Generate HTML with summaries
        html_file = f"{file_prefix}_speaker_summaries.html"
        summary_file = f"{file_prefix}_meeting_summaries.html"
        status.update("html", "Generated HTML with summaries...", 30)
        speaker_summary_file = f"{file_prefix}_speaker_summaries.md"
        meeting_summary_md_file = f"{file_prefix}_meeting_summaries.md"
        
        # Use enhanced summaries by default unless explicitly disabled
        use_enhanced_summaries = not options.get("no_enhanced_summaries", False)
        
        # Important: This matches how fullpipeline.py calls process_xlsx
        try:
            result_files = xlsx2html.process_xlsx(
                xlsx_file,
                video_id,
                html_file, 
                speaker_summary_file,
                meeting_summary_md_file,
                use_enhanced_summaries=use_enhanced_summaries
            )
            status.update("html", "Created HTML with speaker summaries...", 90)
            
            # Unpack result files if available
            if result_files:
                html_file, summary_file, speaker_summary_file, meeting_summary_md_file, mantis_file = result_files
                status.add_output_file("mantis_xlsx", mantis_file)
            #endif
                    
        except Exception as e:
            logger.error(f"Error in xlsx2html processing: {e}")
            status.update("html", f"Warning: Error in HTML generation: {str(e)}", 90)
            status.update("proceeding", "Proceeding with available files...", 90)
        
        # Convert markdown-style bold formatting to HTML bold tags by default
        if not options.get("skip_bold_conversion", False) and html_bold_converter:
            status.update("formatting", "Converting markdown bold to HTML tags...", 95)
            
            # Process HTML files
            if os.path.exists(html_file):
                html_bold_converter.process_html_file(html_file)
                status.update("formatting", "Converted bold formatting in speaker summaries HTML", 96)
                
            if os.path.exists(summary_file):
                html_bold_converter.process_html_file(summary_file)
                status.update("formatting", "Converted bold formatting in meeting summaries HTML", 97)
                
            # Process Markdown files
            if os.path.exists(speaker_summary_file):
                html_bold_converter.process_md_file(speaker_summary_file)
                status.update("formatting", "Converted bold formatting in speaker summaries MD", 98)
                
            if os.path.exists(meeting_summary_md_file):
                html_bold_converter.process_md_file(meeting_summary_md_file)
                status.update("formatting", "Converted bold formatting in meeting summaries MD", 99)
        
        status.update("completed", "Processing completed successfully!", 100)
        
        # Add output files to status
        status.add_output_file("srt", srt_file)
        status.add_output_file("txt", txt_file)
        status.add_output_file("xlsx", xlsx_file)
        status.add_output_file("html", html_file)
        status.add_output_file("summary_html", summary_file)
        status.add_output_file("speaker_summary_md", speaker_summary_file)
        status.add_output_file("meeting_summary_md", meeting_summary_md_file)
        
        # Return to original directory
        os.chdir(original_dir)
        
    except Exception as e:
        status.set_error(str(e))
        logger.error(f"Error in process_url: {e}")
        # Return to original directory
        if 'original_dir' in locals():
            os.chdir(original_dir)

def process_git_job(job_id, repo_urls, username, start_date, end_date=None):
    """Process Git Repos for Daily Standup or Range Report"""
    status = processing_jobs[job_id]
    
    # Determine display date string
    date_str = start_date
    if end_date and end_date != start_date:
        date_str = f"{start_date}_to_{end_date}"
    
    try:
        # Create job directory
        job_dir = os.path.join(app.config['UPLOAD_FOLDER'], job_id)
        os.makedirs(job_dir, exist_ok=True)
        
        # Change to job directory
        original_dir = os.getcwd()
        os.chdir(job_dir)
        
        # 1. Fetch Changes via API (No Cloning)
        target_user = username if username else "ALL USERS"
        
        # Handle single URL string case just in case
        if isinstance(repo_urls, str):
            repo_urls = [repo_urls]

        all_commits = []
        
        for i, url in enumerate(repo_urls):
            url = url.strip()
            if not url: continue
            
            status.update("extracting", f"Fetching commits from {url} ({i+1}/{len(repo_urls)})...", 20 + int(20 * (i/len(repo_urls))))
            commits = git_ops.fetch_repo_changes(url, username, start_date, end_date)
            if commits:
                all_commits.extend(commits)
        
        if not all_commits:
            status.set_error(f"No commits found for {target_user} on {date_str} (or API error)")
            os.chdir(original_dir)
            return

        status.update("parsing", f"Successfully retrieved {len(all_commits)} commits from {len(repo_urls)} repos.", 60)
        
        # Save raw data
        output_file_json = f"standup_{date_str}.json"
        with open(output_file_json, 'w') as f:
            json.dump(all_commits, f, indent=2)
            
        status.add_output_file("json", output_file_json)

        # 2. Generate CSV Stats
        status.update("csv", "Generating statistics CSV...", 70)
        csv_filename = f"git_stats_{date_str}.csv"
        
        try:
            with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                # Header: Repo, file name, file path, num additions, num deletions, author-name, co-authors, date , changes, status
                writer.writerow(['Repository', 'File Name', 'File Path', 'Additions', 'Deletions', 'Author', 'Co-Authors', 'Date', 'Changes', 'Status'])
                
                for commit in all_commits:
                    repo_name = commit.get('repo', 'Unknown')
                    author = commit.get('author', 'Unknown')
                    date = commit.get('timestamp', '')
                    stats = commit.get('file_stats', [])
                    co_authors = commit.get('co-author', '').split(', ') if commit.get('co-author') else []
                    
                    for stat in stats:
                        writer.writerow([
                            repo_name,
                            stat.get('filename', ''),
                            stat.get('filepath', ''),
                            stat.get('additions', 0),
                            stat.get('deletions', 0),
                            author,
                            ', '.join(co_authors),
                            date,
                            stat.get('changes', ''),
                            stat.get('status', '')
                        ])
            
            status.add_output_file("csv", csv_filename)
        except Exception as e:
            logger.error(f"Failed to create CSV: {e}")
            status.update("csv", f"Warning: Failed to create CSV: {e}", 70)
        
        # 3. Generate AI Summary
        status.update("summarizing", "Generating AI Activity Report...", 80)
        
        # Get API Key
        #api_key = os.getenv("API_KEY")
        
        # 3a. Get Structured Data (JSON)
        # Pass the date range string for context
        display_date = f"{start_date} to {end_date}" if end_date else start_date
        #summary_data = git_summarizer.generate_standup_summary(all_commits, display_date, api_key)
        
        # Save Structured JSON
        summary_json_file = f"standup_summary_{date_str}.json"
        with open(summary_json_file, 'w') as f:
            # for debugging purposes, we skip AI summary generation
            json.dump({"results": {}}, f, indent=2)
            #json.dump(summary_data, f, indent=2)
        status.add_output_file("summary_json", summary_json_file)
        
        # 3b. Generate HTML Report
        html_file = f"standup_{date_str}.html"
        #git_summarizer.generate_git_html(summary_data, display_date, repo_urls, html_file)
        git_summarizer.generate_git_html({"results": {}}, display_date, repo_urls, html_file)  # skip AI summary for now
        status.add_output_file("html", html_file)
        
        # 3c. Generate Markdown Report
        md_file = f"standup_{date_str}.md"
        #git_summarizer.generate_git_markdown(summary_data, display_date, md_file)
        git_summarizer.generate_git_markdown({"results": {}}, display_date, md_file)  # skip AI summary for now
        status.add_output_file("markdown", md_file)
        
        status.update("completed", "Git processing completed", 100)
        os.chdir(original_dir)

    except Exception as e:
        status.set_error(str(e))
        logger.error(f"Error in process_git_job: {e}")
        if 'original_dir' in locals():
            os.chdir(original_dir)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    # Check request type
    req_type = request.form.get('type', 'video')

    # Generate a unique job ID
    job_id = str(uuid.uuid4())
    processing_jobs[job_id] = ProcessingStatus()

    if req_type == 'git':
        repo_url_input = request.form.get('repo_url')
        username = request.form.get('git_username')
        date_str = request.form.get('git_date')
        date_end = request.form.get('git_date_end') # Optional end date
        
        # Username is now optional
        if not repo_url_input or not date_str:
             return jsonify({"error": "Missing Git parameters (Repo URL and Start Date are required)"}), 400
             
        # Split URLs by comma or newline
        repo_urls = [url.strip() for url in repo_url_input.replace(',', '\n').split('\n') if url.strip()]
        
        target_log = username if username else "ALL USERS"
        display_date = f"{date_str} to {date_end}" if date_end else date_str
        logger.info(f"Starting Git Job: {len(repo_urls)} repos for {target_log} on {display_date}")
        
        thread = threading.Thread(target=process_git_job, args=(job_id, repo_urls, username, date_str, date_end))
        thread.daemon = True
        thread.start()
        
        return jsonify({"job_id": job_id})

    else:
        # EXISTING VIDEO LOGIC
        # Get URL and options from form
        url = request.form.get('url', '')
        
        if not url:
            return jsonify({"error": "No URL provided"}), 400
        
        # Get options
        options = {
            "skip_refinement": request.form.get('skip_refinement') == 'true',
            "language": request.form.get('language', 'English_USA'),
            "no_enhanced_summaries": request.form.get('no_enhanced_summaries') == 'true',
            "skip_bold_conversion": request.form.get('skip_bold_conversion') == 'true'
        }
        
        # Log received options
        logger.info(f"Processing with options: {options}")
        
        # Start processing in a background thread
        thread = threading.Thread(target=process_url, args=(job_id, url, options))
        thread.daemon = True
        thread.start()
        
        return jsonify({"job_id": job_id})

@app.route('/status/<job_id>', methods=['GET'])
def status(job_id):
    if job_id not in processing_jobs:
        return jsonify({"error": "Job not found"}), 404
    
    return jsonify(processing_jobs[job_id].to_dict())

@app.route('/download/<job_id>/<file_type>', methods=['GET'])
def download(job_id, file_type):
    if job_id not in processing_jobs:
        return jsonify({"error": "Job not found"}), 404
    
    status = processing_jobs[job_id]
    
    if file_type not in status.output_files:
        return jsonify({"error": "File not found"}), 404
    
    file_path = status.output_files[file_type]
    job_dir = os.path.join(app.config['UPLOAD_FOLDER'], job_id)
    full_path = os.path.join(job_dir, file_path)
    
    if not os.path.exists(full_path):
        return jsonify({"error": "File not found on server"}), 404
    
    return send_file(full_path, as_attachment=True)

@app.route('/cleanup/<job_id>', methods=['POST'])
def cleanup(job_id):
    if job_id not in processing_jobs:
        return jsonify({"error": "Job not found"}), 404
    
    job_dir = os.path.join(app.config['UPLOAD_FOLDER'], job_id)
    
    # Remove the job directory
    if os.path.exists(job_dir):
        shutil.rmtree(job_dir)
    
    # Remove job from tracking
    del processing_jobs[job_id]
    
    return jsonify({"success": True})

# --- Auth Routes ---

# @app.route('/login')
# def login_page():
#     # If already logged in, go to index
#     if 'user' in session:
#         return redirect(url_for('index'))
#     return render_template('login.html')

# @app.route('/auth/<provider>')
# def login(provider):
#     # Define your public base URL (default to localhost for dev)
#     base_url = os.getenv("APP_BASE_URL", "http://localhost:5001")
    
#     # Construct the callback URL manually
#     redirect_uri = f"{base_url}/auth/{provider}/callback"
    
#     return oauth.create_client(provider).authorize_redirect(redirect_uri)

# @app.route('/auth/<provider>/callback')
# def auth_callback(provider):
#     client = oauth.create_client(provider)
#     token = client.authorize_access_token()  # This contains the access_token
    
#     user_info = None
#     if provider == 'google':
#         user_info = token.get('userinfo')
#     elif provider == 'github':
#         resp = client.get('user')
#         user_info = resp.json()
#         if not user_info.get('email'):
#             email_resp = client.get('user/emails')
#             user_info['email'] = email_resp.json()[0]['email']

#     if user_info:
#         session['user'] = user_info
#         # STORE THE TOKEN AND PROVIDER FOR LATER USE
#         session['oauth_token'] = token 
#         session['oauth_provider'] = provider
#         return redirect(url_for('index'))
    
#     return "Authentication failed", 401

# @app.route('/logout')
# def logout():
#     session.pop('user', None)
#     return redirect(url_for('login_page'))

# --- Protect Existing Routes ---

# @app.before_request
# def require_login():
#     # List of routes that don't require login
#     allowed_routes = ['login_page', 'login', 'auth_callback', 'static']
    
#     if request.endpoint not in allowed_routes and 'user' not in session:
#         return redirect(url_for('login_page'))

# Setup automatic cleanup of temp files older than 1 day
@app.before_request
def cleanup_old_jobs():
    # First ensure the directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    now = time.time()
    # Only proceed with cleanup if directory exists
    if os.path.exists(app.config['UPLOAD_FOLDER']):
        for item in os.listdir(app.config['UPLOAD_FOLDER']):
            item_path = os.path.join(app.config['UPLOAD_FOLDER'], item)
            if os.path.isdir(item_path) and now - os.path.getmtime(item_path) > 86400:  # 24 hours
                try:
                    shutil.rmtree(item_path)
                    if item in processing_jobs:
                        del processing_jobs[item]
                except Exception as e:
                    logger.error(f"Error cleaning up directory {item_path}: {e}")

@app.route('/invoke-mantis', methods=['POST'])
def invoke_mantis():
    """
    Forwards the processed meeting data to MantisAPI.
    """
    data = request.json
    job_id = data.get('job_id')
    
    if not job_id or job_id not in processing_jobs:
        return jsonify({"error": "Invalid Job ID"}), 400

    # 1. Get Configuration
    mantis_url = os.getenv('MANTIS_API_URL')
    if not mantis_url:
        return jsonify({"error": "MantisAPI URL not configured"}), 500

    # 2. Locate the file
    status = processing_jobs[job_id]
    
    # Prefer the structured Mantis file, fallback to raw transcript
    file_path = status.output_files.get('mantis_xlsx')
    
    if file_path:
        # Mapping for the Summarized Topics File
        # Columns: Title, Speaker, Time, Seconds, Content, Link
        column_mapping = [
            {"title": True},                    # Title
            {"categoric": True},                # Speaker
            {"categoric": True},                # Time
            {"numeric": True},                  # Seconds
            {"semantic": True},                 # Content
            {"links": True}                     # Link
        ]
    else:
        # Fallback to raw transcript if summarization failed
        file_path = status.output_files.get('xlsx')
        if not file_path:
            return jsonify({"error": "No suitable Excel file found."}), 404
            
        # Mapping for Raw Transcript
        # Columns: Seconds, Time, Name, Text
        column_mapping = [
            {"numeric": True},                  # Seconds
            {"categoric": True},                # Time
            {"categoric": True},                # Name
            {"semantic": True, "title": True}   # Text
        ]

    full_path = os.path.join(app.config['UPLOAD_FOLDER'], job_id, file_path)

    try:
        # 3. Prepare Multipart Upload
        with open(full_path, 'rb') as f:
            files = {
                'file': (file_path, f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            }
            
            form_data = {
                'user_id': str('dd585847-d8ec-5f53-ac1b-72c01f80652a'),# alex-d4v user id
                'map_name': f"Meeting {job_id}",
                'space_name': f"Auto Meeting Minutes {str(time.strftime('%Y-%m-%d'))}",
                'data_types': json.dumps(column_mapping),
                'is_public': 'false',
                # --- ADDED FIELDS TO MATCH FRONTEND ---
                'ai_provider': 'openai',
                'embedding_service': 'openai-embeddings',
                'chat_service': 'openai-chat'
            }

            # FIX: Update endpoint to match upload_backend.tsx (/synthesis/landscape/)
            target_endpoint = f"{mantis_url}/synthesis/landscape/" 
            
            logger.info(f"Sending {file_path} to MantisAPI Landscape at {target_endpoint}")
            
            response = requests.post(
                target_endpoint, 
                files=files, 
                data=form_data, 
                timeout=60
            )
        
        if response.status_code in [200, 201]:
            mantis_data = response.json()
            space_id = mantis_data.get('space_id')
            map_id = mantis_data.get('map_id')
            
            # Construct the Frontend URL for redirection
            frontend_base = os.getenv('MANTIS_FRONTEND_URL', 'http://localhost:3000')
            redirect_url = f"{frontend_base}/progress/synthesis_csv/{space_id}/{map_id}"
    
            return jsonify({
                "success": True, 
                "message": "Successfully created Landscape in Mantis",
                "map_id": map_id,
                "redirect_url": redirect_url,
                "mantis_response": mantis_data
            })
        else:
            logger.error(f"MantisAPI Error: {response.status_code} - {response.text}")
            return jsonify({
                "error": f"MantisAPI rejected request: {response.status_code}",
                "details": response.text
            }), 502

    except Exception as e:
        logger.error(f"Failed to invoke MantisAPI: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Log API model and key status
    api_key = os.getenv("API_KEY")
    model = os.getenv("GPT_MODEL", "Not set - will use default")
    logger.info(f"Using API model: {model}")
    logger.info(f"API Key configured: {'Yes' if api_key else 'No - summaries will be limited'}")
    
    # In Docker, we want to listen on all interfaces
    app.run(debug=False, threaded=True, host='0.0.0.0', port=5001)