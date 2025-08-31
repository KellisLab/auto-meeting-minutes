
import os
import shutil
import tempfile
from celery import Celery
from fullpipeline import run_pipeline_from_url

app = Celery('fullpipeline')
app.conf.broker_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')

app.conf.beat_schedule = {
    'process-meetings': {
        'task': 'celery_tasks.process_meetings',
        'schedule': 3600.0,  # hourly
    },
}

@app.task
def process_meetings():
    """Process meetings and copy all outputs to mantisapi static directory"""
    MANTISAPI_STATIC_PATH = os.getenv('MANTISAPI_STATIC_PATH')
    MEETING_URLS = os.getenv('MEETING_URLS', '').split(',')
    
    if not MANTISAPI_STATIC_PATH:
        print("Error: MANTISAPI_STATIC_PATH environment variable not set")
        return "Error: Missing static path configuration"
    
    if not MEETING_URLS or not MEETING_URLS[0].strip():
        print("Error: No meeting URLs configured")
        return "Error: No meeting URLs configured"
    
    # Ensure static directory exists
    os.makedirs(MANTISAPI_STATIC_PATH, exist_ok=True)
    
    processed_count = 0
    failed_count = 0
    
    for url in MEETING_URLS:
        url = url.strip()
        if not url:
            continue
            
        print(f"Processing meeting: {url}")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Run fullpipeline to process the meeting
                result_files = run_pipeline_from_url(
                    url, 
                    meeting_root=temp_dir,
                    skip_refinement=False,
                    skip_timestamps=False,
                    skip_bold_conversion=False,
                    use_enhanced_summaries=True
                )
                
                # Copy all generated files to static directory
                meeting_dir = result_files['meeting_dir']
                video_id = result_files['video_id']
                
                # Create a subdirectory for this meeting in static
                static_meeting_dir = os.path.join(MANTISAPI_STATIC_PATH, video_id)
                os.makedirs(static_meeting_dir, exist_ok=True)
                
                # Copy all files from the meeting directory
                for filename in os.listdir(meeting_dir):
                    src = os.path.join(meeting_dir, filename)
                    dst = os.path.join(static_meeting_dir, filename)
                    
                    if os.path.isfile(src):  # Only copy files, not subdirectories
                        shutil.copy2(src, dst)
                        print(f"  Copied: {filename}")
                
                print(f"✓ Successfully processed and copied meeting {video_id}")
                processed_count += 1
                
            except Exception as e:
                print(f"✗ Failed to process {url}: {e}")
                failed_count += 1
    
    result = f"Processed {processed_count} meetings successfully"
    if failed_count > 0:
        result += f", {failed_count} failed"
    
    print(f"Final result: {result}")
    return result