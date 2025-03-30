from flask import Flask, render_template, request, jsonify, send_file, session
import os
import uuid
import threading
import time
import importlib.util
import sys
from pathlib import Path
import shutil
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management
app.config['UPLOAD_FOLDER'] = 'temp_files'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size

# Ensure temp directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Keep track of active processing jobs
processing_jobs = {}

# Import pipeline modules from current directory
def import_module_from_file(module_name, file_path):
    """Import a module from a file path"""
    if not os.path.exists(file_path):
        return None
        
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# Import necessary modules from the pipeline
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    url2id = import_module_from_file("url2id", os.path.join(script_dir, "url2id.py"))
    url2meeting_name = import_module_from_file("url2meeting_name", os.path.join(script_dir, "url2meeting_name.py"))
    url2file = import_module_from_file("url2file", os.path.join(script_dir, "url2file.py"))
    vtt2txt = import_module_from_file("vtt2txt", os.path.join(script_dir, "vtt2txt.py"))
    txt2xlsx = import_module_from_file("txt2xlsx", os.path.join(script_dir, "txt2xlsx.py"))
    refineStartTimes = import_module_from_file("refineStartTimes", os.path.join(script_dir, "refineStartTimes.py"))
    xlsx2html = import_module_from_file("xlsx2html", os.path.join(script_dir, "xlsx2html.py"))
    fullpipeline = import_module_from_file("fullpipeline", os.path.join(script_dir, "fullpipeline.py"))
except Exception as e:
    print(f"Error importing pipeline modules: {e}")
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
        # Extract video ID
        video_id = url2id.extract_id_from_url(url)
        if not video_id:
            status.set_error("Could not extract a valid video ID from the URL")
            os.chdir(original_dir)
            return
        
        status.update("extracting_name", "Extracting meeting name from URL...", 10)
        # Extract meeting name
        meeting_name = url2meeting_name.get_meeting_name_from_viewer_page(url)
        if not meeting_name:
            status.update("name_fallback", "Could not extract meeting name, using video ID as fallback", 15)
            file_prefix = video_id
        else:
            # Sanitize meeting name for filenames
            file_prefix = fullpipeline.sanitize_filename(meeting_name)
            status.update("name_extracted", f"Extracted meeting name: {meeting_name}", 15)
        
        status.update("downloading", "Downloading transcript...", 20)
        # Download transcript
        srt_file = f"{file_prefix}.srt"
        language = options.get("language", "English_USA")
        
        if not url2file.download_transcript(video_id, srt_file, language):
            status.set_error("Failed to download transcript")
            os.chdir(original_dir)
            return
        
        status.update("converting", "Converting SRT to TXT...", 30)
        # Convert SRT to TXT
        txt_file = f"{file_prefix}.txt"
        txt_file = vtt2txt.vtt_to_txt(srt_file, txt_file)
        
        status.update("excel", "Converting TXT to Excel format...", 40)
        # Convert TXT to XLSX
        xlsx_file = f"{file_prefix}.xlsx"
        xlsx_file = txt2xlsx.txt_to_xlsx(txt_file, xlsx_file)
        
        # Refine start times if not skipped
        if not options.get("skip_refinement", False):
            status.update("refining", "Refining start times...", 50)
            refined_xlsx_file = f"{file_prefix}_refined.xlsx"
            refined_xlsx_file = refineStartTimes.refine_start_times(xlsx_file, refined_xlsx_file)
        else:
            status.update("skipping", "Skipping refinement step...", 50)
            refined_xlsx_file = xlsx_file
        
        status.update("html", "Generating HTML with summaries...", 60)
        # Generate HTML with summaries
        html_format = options.get("html_format", "numbered")
        html_file = f"{file_prefix}_speaker_summaries.html"
        summary_file = f"{file_prefix}_meeting_summaries.html"
        speaker_summary_file = f"{file_prefix}_speaker_summaries.md"
        meeting_summary_md_file = f"{file_prefix}_meeting_summaries.md"
        
        # Process the refined Excel file
        html_file, summary_file, speaker_summary_file, meeting_summary_md_file = xlsx2html.process_xlsx(
            refined_xlsx_file,
            video_id,
            html_file,
            html_format,
            summary_file,
            speaker_summary_file,
            meeting_summary_md_file
        )
        
        status.update("completed", "Processing completed successfully!", 100)
        
        # Add output files to status
        status.add_output_file("srt", srt_file)
        status.add_output_file("txt", txt_file)
        status.add_output_file("xlsx", xlsx_file)
        if refined_xlsx_file != xlsx_file:
            status.add_output_file("refined_xlsx", refined_xlsx_file)
        status.add_output_file("html", html_file)
        status.add_output_file("summary_html", summary_file)
        status.add_output_file("speaker_summary_md", speaker_summary_file)
        status.add_output_file("meeting_summary_md", meeting_summary_md_file)
        
        # Return to original directory
        os.chdir(original_dir)
        
    except Exception as e:
        status.set_error(str(e))
        # Return to original directory
        if 'original_dir' in locals():
            os.chdir(original_dir)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    # Get URL and options from form
    url = request.form.get('url', '')
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    # Get options
    options = {
        "skip_refinement": request.form.get('skip_refinement') == 'true',
        "html_format": request.form.get('html_format', 'numbered'),
        "language": request.form.get('language', 'English_USA')
    }
    
    # Generate a unique job ID
    job_id = str(uuid.uuid4())
    
    # Create a status object for this job
    processing_jobs[job_id] = ProcessingStatus()
    
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
                shutil.rmtree(item_path)
                if item in processing_jobs:
                    del processing_jobs[item]

# if __name__ == '__main__':
#     app.run(debug=True, threaded=True)
if __name__ == '__main__':
    # In Docker, we want to listen on all interfaces
    app.run(debug=False, threaded=True, host='0.0.0.0', port =5001)