
import os
import shutil
import tempfile
import requests
import json
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from celery import Celery, shared_task

# Setup Django path and environment
current_dir = Path(__file__).resolve().parent

# Add the current directory to Python path so Django can find the apps
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# Setup Django
import django
from django.conf import settings

# Configure Django settings if not already configured
if not settings.configured:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_settings')
    django.setup()

# Import Django utilities and models after Django is configured
from django.utils import timezone
from django.db import transaction
from mantis4mantis.models import Meeting, MeetingTranscript, Member

# Import fullpipeline if available
try:
    from fullpipeline import run_pipeline_from_url
    FULLPIPELINE_AVAILABLE = True
except ImportError:
    FULLPIPELINE_AVAILABLE = False

app = Celery('fullpipeline')
app.conf.broker_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')

from celery.schedules import crontab

app.conf.beat_schedule = {
    'process-meetings': {
        'task': 'celery_tasks.process_meetings',
        'schedule': 3600.0,  # hourly
    },
    'sync-panopto-meetings-daily': {
        'task': 'sync_panopto_meetings_bulk_task',
        'schedule': crontab(minute='0', hour=1),  # Daily at 1 AM
        'kwargs': {
            'folder_id': os.getenv('PANOPTO_FOLDER_ID', '09a9e158-5bb9-4b02-afe9-af8700120f9c'),
            'test_mode': False,
        },
    },
}

@shared_task(name='sync_panopto_meetings_bulk_task')
def sync_panopto_meetings_bulk_task(folder_id: str,
                                   test_mode: bool = False) -> Dict[str, Any]:
    """Standalone task to sync all Panopto meetings from a folder."""
    print(f"Starting bulk Panopto meetings sync for folder: {folder_id}")
    
    try:
        meetings = get_meetings_from_folder(folder_id)
        
        if not meetings:
            print("No meetings found in folder")
            return {
                'status': 'success',
                'completed_at': timezone.now().isoformat(),
                'message': 'No meetings found in folder',
                'folder_id': folder_id,
                'stats': {'processed': 0, 'skipped': 0, 'failed': 0}
            }
        
        if test_mode:
            meetings = meetings[:16]
            print(f"Test mode - processing only first {len(meetings)} meetings")
        
        print(f"Found {len(meetings)} meetings:")
        for i, meeting in enumerate(meetings, 1):
            print(f"  {i}. {meeting['name']}")
        
        processed_count = 0
        skipped_count = 0
        failed_count = 0
        
        for i, meeting in enumerate(meetings, 1):
            print(f"Processing meeting {i}/{len(meetings)}: {meeting['name']}")
            
            try:
                if Meeting.objects.filter(panopto_id=meeting['id']).exists():
                    print(f"  Meeting {meeting['id']} already exists, skipping...")
                    skipped_count += 1
                    continue
                
                process_single_meeting(meeting['url'], meeting['name'], meeting.get('meeting_date'))
                
                processed_count += 1
                print(f"  ✓ Successfully processed: {meeting['name']}")
                
            except Exception as e:
                print(f"  ✗ Failed to process {meeting['name']}: {e}")
                failed_count += 1
                continue
        
        print("✓ Bulk Panopto meetings sync completed successfully")
        print(f"  Total meetings: {len(meetings)}")
        print(f"  Processed: {processed_count}")
        print(f"  Skipped: {skipped_count}")
        print(f"  Failed: {failed_count}")
        
        return {
            'status': 'success',
            'completed_at': timezone.now().isoformat(),
            'message': f'Bulk Panopto meetings sync completed successfully for folder {folder_id}',
            'folder_id': folder_id,
            'test_mode': test_mode,
            'stats': {
                'total': len(meetings),
                'processed': processed_count,
                'skipped': skipped_count,
                'failed': failed_count
            }
        }
        
    except Exception as e:
        error_msg = f"Bulk Panopto meetings sync failed: {e!s}"
        print(f"✗ {error_msg}")
        
        import traceback
        traceback.print_exc()
        
        return {
            'status': 'error',
            'completed_at': timezone.now().isoformat(),
            'error': str(e),
            'error_type': type(e).__name__,
            'traceback': traceback.format_exc(),
            'message': error_msg,
            'folder_id': folder_id,
        }


def get_meetings_from_folder(folder_id):
    """Get all meetings from a Panopto folder."""
    print("Loading Panopto folder with API...")
    
    url = "https://mit.hosted.panopto.com/Panopto/Services/Data.svc/GetSessions"
    
    payload = json.dumps({
        "queryParameters": {
            "query": None,
            "sortColumn": 1,
            "sortAscending": False,
            "maxResults": 1000000,
            "page": 0,
            "startDate": None,
            "endDate": None,
            "folderID": folder_id,
            "bookmarked": False,
            "getFolderData": True,
            "isSharedWithMe": False,
            "isSubscriptionsPage": False,
            "includeArchived": True,
            "includeArchivedStateCount": False,
            "sessionListOnlyArchived": False,
            "includePlaylists": True,
        },
    })
    
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/json',
        'origin': 'https://mit.hosted.panopto.com',
        'priority': 'u=1, i',
        'referer': 'https://mit.hosted.panopto.com/Panopto/Pages/Sessions/List.aspx',
        'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
        'Cookie': 'UserSettings=AnonymousUserID=cda77c23-c1a6-4e99-b77e-b2f8015e5551&LastLoginMembershipProvider=; _ga_PY0JL6PVQ2=GS2.1.s1751889283$o1$g1$t1751889295$j48$l0$h0; _fbp=fb.1.1751889296825.417009967742659293; _gcl_au=1.1.269266119.1751889296.658113623.1751889300.1751889299; _ga_01EVE3NLBP=GS2.1.s1751889296$o1$g1$t1751890542$j59$l0$h1771253211; _ga=GA1.2.894516955.1749590131; _uetvid=33ef77b05b2911f0992aa3f48c8aca5f|1x2mfon|1751890543154|2|1|bat.bing.com/p/conversions/c/l; _ga_ZC373MMXMD=GS2.2.s1753875289$o14$g1$t1753875328$j21$l0$h0; _gid=GA1.2.1013678389.1754312057; _ga_8337TM8N21=GS2.2.s1754312725$o21$g0$t1754312725$j60$l0$h0; _ga_THQJRFNFBN=GS2.2.s1754312057$o11$g1$t1754312943$j60$l0$h0',
    }
    
    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()
        
        data = response.json()
        
        meetings = []
        if 'd' in data and 'Results' in data['d']:
            for session in data['d']['Results']:
                if 'ViewerUrl' in session and 'SessionName' in session:
                    viewer_url = session['ViewerUrl']
                    session_name = session['SessionName']
                    
                    # Extract ID from viewer URL
                    video_id_match = re.search(r'id=([a-f0-9-]{36})', viewer_url)
                    if video_id_match:
                        video_id = video_id_match.group(1)
                        
                        # Extract meeting date from API response
                        meeting_date = None
                        if session.get('StartTime'):
                            try:
                                start_time_str = session['StartTime']
                                if start_time_str.startswith('/Date(') and start_time_str.endswith(')/'):
                                    timestamp_str = start_time_str[6:-2]
                                    timestamp_ms = int(timestamp_str)
                                    timestamp_sec = timestamp_ms / 1000
                                    meeting_date = datetime.fromtimestamp(timestamp_sec)
                                    print(f"  API date extracted for '{session_name}': {meeting_date}")
                            except (ValueError, TypeError) as e:
                                print(f"  Warning: Could not parse StartTime '{session['StartTime']}' for '{session_name}': {e}")
                        
                        if not meeting_date:
                            meeting_date = extract_meeting_date(session_name)
                            print(f"  Title date extracted for '{session_name}': {meeting_date}")
                        
                        meetings.append({
                            'id': video_id,
                            'url': viewer_url,
                            'name': session_name,
                            'created': meeting_date.strftime('%Y-%m-%d') if meeting_date else datetime.now().strftime('%Y-%m-%d'),
                            'meeting_date': meeting_date,
                        })
        
        print(f"Found {len(meetings)} sessions via API")
        return meetings
        
    except requests.RequestException as e:
        raise Exception(f"Error fetching sessions from Panopto API: {e}")
    except (KeyError, json.JSONDecodeError) as e:
        raise Exception(f"Error parsing Panopto API response: {e}")


def extract_meeting_date(meeting_name):
    """Extract date from meeting name."""
    if not meeting_name or meeting_name.strip() == "":
        print("  Warning: Could not extract date because meeting name is empty or None.")
        return timezone.now()

    print(f"  Parsing date from: '{meeting_name}'")
    
    # Match format like "2025-07-28 Mon10Am" or "2025-08-02 Sat12Pm"
    pattern = r'(\d{4})-(\d{1,2})-(\d{1,2})\s+[A-Za-z]{3}(\d{1,2})([AaPp][Mm])'
    match = re.search(pattern, meeting_name, re.IGNORECASE)
    if match:
        try:
            year, month, day = map(int, match.groups()[:3])
            hour = int(match.group(4))
            am_pm = match.group(5).lower()
            
            if am_pm == 'pm' and hour != 12:
                hour += 12
            elif am_pm == 'am' and hour == 12:
                hour = 0
            
            result = timezone.make_aware(datetime(year, month, day, hour, 0))
            print(f"  Successfully parsed: {result}")
            return result
        except Exception as e:
            print(f"  Error parsing date components: {e}")

    # Try other date patterns...
    patterns = [
        r'(\d{4})-(\d{1,2})-(\d{1,2})',   # YYYY-MM-DD
        r'(\d{4})\.(\d{1,2})\.(\d{1,2})',  # YYYY.MM.DD
        r'(\d{4})/(\d{1,2})/(\d{1,2})',   # YYYY/MM/DD
    ]
    for pattern in patterns:
        match = re.search(pattern, meeting_name)
        if match:
            try:
                year, month, day = map(int, match.groups())
                result = timezone.make_aware(datetime(year, month, day))
                print(f"  Successfully parsed date only: {result}")
                return result
            except ValueError:
                continue

    print(f"  Warning: Could not extract date from '{meeting_name}', using current time")
    return timezone.now()


def process_single_meeting(meeting_url, meeting_name, meeting_date=None):
    """Process a single meeting using the full pipeline."""
    # Load meeting-notes modules dynamically
    meeting_notes_modules = load_meeting_notes_modules()
    
    try:
        # Extract video ID
        video_id = extract_id_from_url(meeting_url)
        if not video_id:
            raise Exception(f"Could not extract video ID from URL: {meeting_url}")
        
        print(f"  Extracted video ID: {video_id}")
        
        # Check if meeting already exists
        if Meeting.objects.filter(panopto_id=video_id).exists():
            existing_meeting = Meeting.objects.get(panopto_id=video_id)
            
            # Try to get better meeting name
            try:
                new_meeting_name = extract_meeting_name_from_url(meeting_url)
            except:
                new_meeting_name = f"Meeting {video_id[:8]}"
            
            if not new_meeting_name or new_meeting_name == "None":
                new_meeting_name = f"Meeting {video_id[:8]}"
            
            new_meeting_name = clean_meeting_name(new_meeting_name)
            
            if should_update_meeting_name(existing_meeting, new_meeting_name):
                print(f"  Updating existing meeting with better name: '{existing_meeting.title}' -> '{new_meeting_name}'")
                
                meeting_category = extract_meeting_category(new_meeting_name)
                
                existing_meeting.title = new_meeting_name
                if meeting_category:
                    existing_meeting.team_name = meeting_category
                    existing_meeting.meeting_type = meeting_category
                existing_meeting.save()
                
                print(f"  Updated meeting: {existing_meeting}")
            else:
                print(f"  Meeting with Panopto ID {video_id} already exists: '{existing_meeting.title}'.")
            
            # Check if transcript exists for this meeting
            if not MeetingTranscript.objects.filter(meeting=existing_meeting).exists():
                print(f"  No transcript found, downloading...")
                srt_content = download_transcript(video_id)
                
                if srt_content:
                    # Parse SRT into segments
                    segments = parse_srt_to_segments(srt_content)
                    
                    if segments:
                        # Group segments by speaker
                        speaker_segments = group_segments_by_speaker(segments)
                        
                        print(f"  Found {len(speaker_segments)} speaker segments")
                        
                        # Create MeetingTranscript records for each speaker segment
                        for segment in speaker_segments:
                            # Try to match speaker to existing Member
                            speaker_member = None
                            try:
                                speaker_member = Member.objects.filter(
                                    name__icontains=segment['speaker_name']
                                ).first()
                            except:
                                pass
                            
                            transcript = MeetingTranscript.objects.create(
                                meeting=existing_meeting,
                                speaker=speaker_member,
                                speaker_name=segment['speaker_name'],
                                content=segment['content'],
                                start_time=segment['start_time'],
                                end_time=segment['end_time']
                            )
                        
                        print(f"  ✓ Added {len(speaker_segments)} transcript segments")
                    else:
                        print(f"  ✗ No transcript segments found")
                else:
                    print(f"  ✗ Failed to download transcript")
            else:
                print(f"  Transcript already exists, skipping.")
            
            return
        
        # Get meeting name from viewer page
        try:
            meeting_name = extract_meeting_name_from_url(meeting_url)
        except:
            meeting_name = f"Meeting {video_id[:8]}"
        
        if not meeting_name or meeting_name == "None":
            meeting_name = f"Meeting {video_id[:8]}"
        
        if is_generic_meeting_name(meeting_name):
            print(f"  Skipping generic meeting name: '{meeting_name}'. Likely a duplicate or placeholder.")
            return
        
        meeting_name = clean_meeting_name(meeting_name)
        
        print(f"  Meeting name: {meeting_name}")
        
        # Extract meeting date
        if not meeting_date:
            meeting_date = extract_meeting_date(meeting_name)
        print(f"  Meeting date: {meeting_date}")
        
        # Extract meeting category
        meeting_category = extract_meeting_category(meeting_name)
        if meeting_category:
            print(f"  Meeting category: {meeting_category}")
        
        # Process with full pipeline (simplified for DB creation)
        with transaction.atomic():
            meeting_date_obj = meeting_date
            if not meeting_date_obj or isinstance(meeting_date_obj, str):
                print(f"  Warning: Could not parse meeting date from title '{meeting_name}', using current time.")
                meeting_date_obj = timezone.now()
            
            meeting = Meeting.objects.create(
                title=meeting_name,
                panopto_id=video_id,
                panopto_url=meeting_url,
                meeting_date=meeting_date_obj,
                team_name=meeting_category,
                meeting_type=meeting_category,
            )
            
            print(f"  Created meeting: {meeting}")
            if meeting_category:
                print(f"    Category: {meeting_category}")
            
            # Download and process transcript
            print(f"  Downloading transcript...")
            srt_content = download_transcript(video_id)
            
            if srt_content:
                # Parse SRT into segments
                segments = parse_srt_to_segments(srt_content)
                
                if segments:
                    # Group segments by speaker
                    speaker_segments = group_segments_by_speaker(segments)
                    
                    print(f"  Found {len(speaker_segments)} speaker segments")
                    
                    # Create MeetingTranscript records for each speaker segment
                    for segment in speaker_segments:
                        # Try to match speaker to existing Member
                        speaker_member = None
                        try:
                            speaker_member = Member.objects.filter(
                                name__icontains=segment['speaker_name']
                            ).first()
                        except:
                            pass
                        
                        transcript = MeetingTranscript.objects.create(
                            meeting=meeting,
                            speaker=speaker_member,
                            speaker_name=segment['speaker_name'],
                            content=segment['content'],
                            start_time=segment['start_time'],
                            end_time=segment['end_time']
                        )
                    
                    print(f"  ✓ Created {len(speaker_segments)} transcript segments")
                else:
                    print(f"  ✗ No transcript segments found")
            else:
                print(f"  ✗ Failed to download transcript")
                
    except Exception as e:
        print(f"  ✗ Error processing meeting: {e}")
        raise


def extract_id_from_url(url):
    """Extract Panopto video ID from a URL."""
    import re
    pattern = r'id=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def extract_meeting_name_from_url(url):
    """Extract meeting name from Panopto viewer page."""
    import requests
    from bs4 import BeautifulSoup
    
    try:
        # Get the viewer page HTML
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # Parse HTML to find the meeting title
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Try multiple selectors to find the title
        title_selectors = [
            'title',
            '.viewer-title',
            '#sessionName',
            '.session-name',
            'h1',
            '[data-testid="session-name"]'
        ]
        
        for selector in title_selectors:
            element = soup.select_one(selector)
            if element:
                title = element.get_text().strip()
                # Clean up the title (remove "Panopto" suffix if present)
                if title and title != "Panopto":
                    title = title.replace(" - Panopto", "").strip()
                    if title:
                        return title
        
        # If no title found, extract video ID and use as fallback
        video_id = extract_id_from_url(url)
        return f"Meeting_{video_id[:8]}" if video_id else "Unknown Meeting"
        
    except Exception as e:
        print(f"  Warning: Could not extract meeting name from URL: {e}")
        video_id = extract_id_from_url(url)
        return f"Meeting_{video_id[:8]}" if video_id else "Unknown Meeting"

def download_transcript(video_id, language="English_USA"):
    """Download transcript for a Panopto video."""
    import requests
    
    # Construct the transcript URL
    transcript_url = f"https://mit.hosted.panopto.com/Panopto/Pages/Transcription/GenerateSRT.ashx?id={video_id}&language={language}"
    
    try:
        # Send GET request to download the transcript
        response = requests.get(transcript_url, timeout=30)
        
        # Check if request was successful
        if response.status_code == 200:
            return response.text
        else:
            print(f"  Warning: Failed to download transcript. Status code: {response.status_code}")
            return None
    
    except Exception as e:
        print(f"  Warning: Error downloading transcript: {e}")
        return None

def parse_srt_to_segments(srt_content):
    """Parse SRT content into individual segments with timestamps and text."""
    import re
    
    if not srt_content:
        return []
    
    segments = []
    lines = srt_content.strip().split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines
        if not line:
            i += 1
            continue
            
        # Check if line is a subtitle number
        if re.match(r'^\d+$', line):
            # Next line should be the timestamp
            i += 1
            if i < len(lines):
                timestamp_line = lines[i].strip()
                # Look for timestamps in format 00:00:00,000 --> 00:00:00,000
                timestamp_match = re.search(r'(\d{2}:\d{2}:\d{2})[,\.]\d{3}\s*-->\s*(\d{2}:\d{2}:\d{2})[,\.]\d{3}', timestamp_line)
                
                if timestamp_match:
                    start_time = timestamp_match.group(1)
                    end_time = timestamp_match.group(2)
                    
                    # Move to the next line which contains the text content
                    i += 1
                    if i < len(lines):
                        text_line = lines[i].strip()
                        if text_line:
                            segments.append({
                                'start_time': start_time,
                                'end_time': end_time,
                                'text': text_line
                            })
        
        # Move to next line
        i += 1
    
    return segments

def group_segments_by_speaker(segments):
    """Group transcript segments by speaker."""
    import re
    
    speaker_segments = []
    current_speaker = None
    current_content = []
    current_start_time = None
    current_end_time = None
    
    for segment in segments:
        text = segment['text']
        
        # Look for speaker patterns like "Speaker Name:" or "Name:"
        speaker_match = re.match(r'^([^:]+):\s*(.*)$', text)
        
        if speaker_match:
            # Save previous speaker's content if exists
            if current_speaker and current_content:
                speaker_segments.append({
                    'speaker_name': current_speaker,
                    'content': ' '.join(current_content),
                    'start_time': current_start_time,
                    'end_time': current_end_time
                })
            
            # Start new speaker
            current_speaker = speaker_match.group(1).strip()
            current_content = [speaker_match.group(2).strip()] if speaker_match.group(2).strip() else []
            current_start_time = segment['start_time']
            current_end_time = segment['end_time']
        else:
            # Continue current speaker's content
            if current_speaker:
                current_content.append(text)
                current_end_time = segment['end_time']  # Update end time
            else:
                # No speaker identified yet, treat as unknown speaker
                if not current_speaker:
                    current_speaker = "Unknown Speaker"
                    current_start_time = segment['start_time']
                current_content.append(text)
                current_end_time = segment['end_time']
    
    # Don't forget the last speaker
    if current_speaker and current_content:
        speaker_segments.append({
            'speaker_name': current_speaker,
            'content': ' '.join(current_content),
            'start_time': current_start_time,
            'end_time': current_end_time
        })
    
    return speaker_segments

def load_meeting_notes_modules():
    """Simple replacement - no external modules needed."""
    return {
        'url2id': type('Module', (), {'extract_id_from_url': extract_id_from_url}),
        'url2meeting_name': type('Module', (), {'extract_meeting_name_from_url': extract_meeting_name_from_url})
    }


def clean_meeting_name(meeting_name):
    """Clean meeting name for display."""
    if not meeting_name:
        return "Unknown Meeting"
    
    cleaned = re.sub(r'\s+', ' ', meeting_name.strip())
    
    # Fix common encoding issues
    cleaned = cleaned.replace('â€™', "'")
    cleaned = cleaned.replace('â€œ', '"')
    cleaned = cleaned.replace('â€', '"')
    cleaned = cleaned.replace('â€"', '-')
    cleaned = cleaned.replace('â€"', '–')
    
    # Remove invalid characters
    cleaned = re.sub(r'[^\w\s\-.,():/]', '', cleaned)
    
    return cleaned.strip()


def is_generic_meeting_name(meeting_name):
    """Check if meeting name is generic."""
    if not meeting_name:
        return True
    
    generic_patterns = [
        r'^Meeting\s+[a-f0-9]{6,}$',
        r'^Meeting\s+[a-f0-9]{8,}$',
        r'^Meeting\s+\d{4,}$',
        r'^Meeting\s+[a-zA-Z0-9]{1,10}$',
        r'^Untitled\s*(Meeting|Session)?',
        r'^Session\s+[a-f0-9]{8,}$',
        r'^Recording\s+\d{4,}$',
        r'^Video\s+[a-f0-9]{8,}$',
    ]
    
    for pattern in generic_patterns:
        if re.match(pattern, meeting_name, re.IGNORECASE):
            return True
    
    if len(meeting_name.strip()) < 10:
        if not any(keyword in meeting_name.lower() for keyword in 
                  ['allhands', 'standup', 'review', 'demo', 'retrospective', 'sync', 
                   'team', 'group', 'squad', 'mantis']) and \
           not re.search(r'\d{4}\.\d{1,2}\.\d{1,2}', meeting_name):
            return True
    
    return False


def should_update_meeting_name(existing_meeting, new_meeting_name):
    """Check if we should update the meeting name."""
    if not new_meeting_name or not existing_meeting.title:
        return False
    
    existing_name = existing_meeting.title
    
    if is_generic_meeting_name(existing_name) and not is_generic_meeting_name(new_meeting_name):
        return True
    
    if re.search(r'\d{4}\.\d{1,2}\.\d{1,2}\s+\w+\d{1,2}(am|pm)', new_meeting_name):
        if (is_generic_meeting_name(existing_name) or 
            not re.search(r'\d{4}\.\d{1,2}\.\d{1,2}\s+\w+\d{1,2}(am|pm)', existing_name)):
            return True
    
    new_has_category = bool(extract_meeting_category(new_meeting_name))
    existing_has_category = bool(extract_meeting_category(existing_name))
    
    if new_has_category and not existing_has_category:
        return True
    
    if len(new_meeting_name) > len(existing_name) * 1.5 and len(existing_name) < 20:
        return True
    
    return False


def extract_meeting_category(meeting_name):
    """Extract meeting category from meeting name - full implementation from DELETE THIS folder."""
    if not meeting_name:
        return None
    
    # Team letters based on your structure
    team_letters = ['A', 'B', 'C', 'D', 'E', 'G', 'H', 'I', 'J', 'K', 'M', 'P']
    
    # Team function keywords
    team_keywords = {
        'A': ['Agents', 'Automation', 'Reinforcement', 'RL', 'Chat'],
        'B': ['Backbone', 'Bedrock', 'Platform', 'Core', 'Interface', 'Features', 'Visual', 'DataScience', 'UI', 'UX', 'Viz'],
        'C': ['Computing', 'Coding', 'Sandbox', 'Notebooks', 'Programming', 'Plotting', 'Bags', 'Performance', 'Networking'],
        'D': ['Embeddings', 'embeDDings', 'Knowledge', 'Graphs', 'Insight', 'Representations', 'Highway', 'Street'],
        'E': ['Expression', 'SingleCell', 'Transcriptomics', 'Quantitative', 'Semantic', 'Functional'],
        'G': ['Genes', 'Proteins', 'Drugs', 'Structure2Function', 'Geo'],
        'H': ['Healthcare', 'EMRs', 'Patient', 'Trajectories', 'Medical'],
        'I': ['Integrations', 'Google', 'Gmail', 'GitHub', 'Panopto', 'Gdocs', 'Gdrive', 'LinkedIn', 'World', 'OpenMarketplace'],
        'J': ['Journeys', 'Protocols', 'Recipes', 'Waypoints', 'Vignettes', 'Reports', 'Insights', 'Teamwork', 'Collab'],
        'K': ['Knowledge', 'kGNN', 'Spreading', 'Activation', 'MultiModal', 'MM', 'ML'],
        'M': ['Mantis4Mantis', 'M4M', 'Enterprise', 'People', 'Management', 'Maps', 'Scraping', 'Refinement'],
        'P': ['IP', 'IntellectualProperty', 'Property', 'Patents'],
    }
    
    # Meeting type patterns
    meeting_types = [
        ('AllHands', r'\b(AllHands|All[_\-\s]?Hands|All[_\-\s]?Hand)\b'),
        ('Standup', r'\b(Standup|Stand[_\-\s]?up|Stand[_\-\s]?Up|Daily)\b'),
        ('Review', r'\b(Review|Code[_\-\s]?Review|PR[_\-\s]?Review)\b'),
        ('Demo', r'\b(Demo|Demonstration)\b'),
        ('Retrospective', r'\b(Retrospective|Retro)\b'),
        ('Planning', r'\b(Planning|Sprint[_\-\s]?Planning)\b'),
        ('Sync', r'\b(Sync|Synchronization)\b'),
        ('Interview', r'\b(Interview|Technical[_\-\s]?Interview)\b'),
        ('Onboarding', r'\b(Onboarding|Training)\b'),
        ('Workshop', r'\b(Workshop|Presentation)\b'),
    ]
    
    # Try hashtag patterns first
    hashtag_pattern = r'#([A-Za-z0-9]+)'
    matches = re.findall(hashtag_pattern, meeting_name)
    if matches:
        valid_teams = []
        for team_code in matches:
            if team_code.upper() in team_letters:
                valid_teams.append(team_code.upper())
            elif team_code in ['Chat', 'W', 'O', 'MM', 'T', 'Vis', 'ML', 'Geo', 'N', 'S', 'R']:
                valid_teams.append(team_code)
        
        if valid_teams:
            if len(valid_teams) == 1:
                if valid_teams[0] in team_letters:
                    print(f"    Extracted hashtag team: Team {valid_teams[0]}")
                    return f"Team {valid_teams[0]}"
                else:
                    print(f"    Extracted hashtag team: #{valid_teams[0]}")
                    return f"#{valid_teams[0]}"
            else:
                combined_team = '#' + ' #'.join(valid_teams)
                print(f"    Extracted combined hashtag teams: {combined_team}")
                return combined_team
    
    # Try explicit team pattern
    team_pattern = r'[Tt]eam\s*([A-Za-z])\b'
    match = re.search(team_pattern, meeting_name)
    if match:
        team_letter = match.group(1).upper()
        if team_letter in team_letters:
            print(f"    Extracted explicit team: Team {team_letter}")
            return f"Team {team_letter}"
    
    # Try keyword matching
    found_teams = []
    for team_letter, keywords in team_keywords.items():
        for keyword in keywords:
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, meeting_name, re.IGNORECASE):
                if team_letter not in found_teams:
                    found_teams.append(team_letter)
                break
    
    if found_teams:
        if len(found_teams) == 1:
            print(f"    Found single team from keywords: Team {found_teams[0]}")
            return f"Team {found_teams[0]}"
        else:
            team_str = "/".join(sorted(found_teams))
            print(f"    Found multiple teams from keywords: Team {team_str}")
            return f"Team {team_str}"
    
    # Check for M4M
    if re.search(r'\bM4M\b', meeting_name, re.IGNORECASE):
        print("    Found M4M: Team M")
        return "Team M"
    
    # Check meeting types
    for meeting_type, pattern in meeting_types:
        match = re.search(pattern, meeting_name, re.IGNORECASE)
        if match:
            print(f"    Found meeting type: {meeting_type}")
            return meeting_type
    
    # Default fallback
    if (re.search(r'\d{4}[\.\-]\d{1,2}[\.\-]\d{1,2}', meeting_name) or
        any(keyword in meeting_name.lower() for keyword in 
            ['meeting', 'discussion', 'session', 'call', 'update', 'brief'])):
        print("    Defaulting to Miscellaneous category")
        return "Miscellaneous"
    
    print(f"    No category found in: {meeting_name}")
    return None

@app.task
def process_meetings():
    """Process meetings and copy all outputs to mantisapi static directory"""
    if not FULLPIPELINE_AVAILABLE:
        return "Error: fullpipeline module not available"
        
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