"""
utils.py - Utility functions for transcript processing pipeline
Contains common helper functions used across multiple scripts.
"""

import os
import re
import sys
import pandas as pd
import numpy as np
import importlib.util
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Constants
OPENAI_API_KEY = os.getenv("API_KEY")
DEFAULT_MODEL = os.getenv("GPT_MODEL", "gpt-4o")
DEFAULT_BATCH_SIZE_MINUTES = 40

# -------------------------------------------------------------
# Time and Timestamp Utilities
# -------------------------------------------------------------

def seconds_to_time_str(seconds):
    """
    Convert seconds to H:MM:SS format (e.g., 0:18:52)
    
    Args:
        seconds (int/float): Number of seconds
        
    Returns:
        str: Formatted time string
    """
    if pd.isna(seconds):
        return "00:00:00"
    
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"

def time_str_to_seconds(time_str):
    """
    Convert H:MM:SS time string to seconds
    
    Args:
        time_str (str): Time string in format H:MM:SS
        
    Returns:
        int: Total seconds
    """
    parts = time_str.split(':')
    if len(parts) == 3:
        hours, minutes, seconds = map(int, parts)
        return hours * 3600 + minutes * 60 + seconds
    else:
        # Handle MM:SS format if needed
        return 0  # Return 0 for invalid formats

def format_corrected_timestamp(seconds):
    """
    Convert seconds to a corrected timestamp string in H:MM:SS format
    
    Args:
        seconds (int): Total seconds
        
    Returns:
        str: Formatted timestamp string
    """
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"

def verify_timestamp_format(timestamp_str, seconds):
    """
    Verify that a timestamp string matches the seconds value
    If not, return a corrected timestamp string
    
    Args:
        timestamp_str (str): Timestamp string in H:MM:SS format
        seconds (int): The seconds value from the URL
        
    Returns:
        str: Corrected timestamp string if needed, or original if already correct
    """
    # Convert timestamp string to seconds
    try:
        parts = timestamp_str.split(':')
        if len(parts) == 3:
            hours, minutes, secs = map(int, parts)
            ts_seconds = hours * 3600 + minutes * 60 + secs
            
            # If they don't match, return a corrected timestamp
            if ts_seconds != seconds:
                return format_corrected_timestamp(seconds)
    except:
        # If parsing fails, return a corrected timestamp
        return format_corrected_timestamp(seconds)
    
    # If already correct or if can't verify, return original
    return timestamp_str

# -------------------------------------------------------------
# Data Extraction and Processing Utilities
# -------------------------------------------------------------

def get_column_letter(col_idx):
    """
    Convert column index to letter (1=A, 2=B, etc.)
    
    Args:
        col_idx (int): Column index (1-based)
        
    Returns:
        str: Column letter(s)
    """
    letter = ''
    while col_idx > 0:
        col_idx, remainder = divmod(col_idx - 1, 26)
        letter = chr(65 + remainder) + letter
    return letter

def extract_transcript_data(df):
    """
    Extract transcript data from the DataFrame
    
    Args:
        df (pandas.DataFrame): The Excel DataFrame
        
    Returns:
        list: List of dictionaries with transcript data
    """
    transcript_data = []
    
    if 'Name' in df.columns and 'Seconds' in df.columns and 'Text' in df.columns:
        for i, row in df.iterrows():
            if pd.notna(row['Name']) and pd.notna(row['Seconds']) and pd.notna(row['Text']):
                entry = {
                    'name': row['Name'],
                    'seconds': int(row['Seconds']),
                    'time_str': seconds_to_time_str(row['Seconds']),
                    'text': row['Text'],
                    'row_index': i  # Add row index for reference
                }
                
                # Add time_end if available (used by refineStartTimes.py)
                if 'End_Seconds' in df.columns and pd.notna(row['End_Seconds']):
                    entry['end_seconds'] = int(row['End_Seconds'])
                    entry['end_time_str'] = seconds_to_time_str(row['End_Seconds'])
                
                # Add topic information if available
                if 'Topic' in df.columns and pd.notna(row['Topic']):
                    entry['topic'] = row['Topic']
                
                # Add matched seconds if available
                if 'Matched_Seconds' in df.columns and pd.notna(row['Matched_Seconds']):
                    entry['matched_seconds'] = int(row['Matched_Seconds'])
                    entry['matched_time_str'] = seconds_to_time_str(row['Matched_Seconds'])
                
                transcript_data.append(entry)
    else:
        raise ValueError("Excel file doesn't contain the expected columns (Name, Seconds, Text)")
    
    # Sort by timestamp
    transcript_data.sort(key=lambda x: x['seconds'])
    return transcript_data

def extract_unique_speakers(df):
    """
    Extract unique speakers from the DataFrame
    First try using 'First' column for first occurrences only,
    then fallback to using all 'Name' entries
    
    Args:
        df (pandas.DataFrame): The Excel DataFrame
        
    Returns:
        list: List of dictionaries with unique speaker data
    """
    speaker_data = []
    
    # First, check if we're using the First columns for unique speakers
    if 'First' in df.columns and 'First_Seconds' in df.columns and df['First'].notna().any():
        unique_speakers = df[df['First'].notna()]
        for i, row in unique_speakers.iterrows():
            if pd.notna(row['First']) and pd.notna(row['First_Seconds']):
                speaker_data.append({
                    'name': row['First'],
                    'seconds': int(row['First_Seconds']),
                    'time_str': seconds_to_time_str(row['First_Seconds']),
                    'row_index': i  # Add row index for reference
                })
    # Fallback to using all rows if no "First" column or no data there
    elif 'Name' in df.columns and 'Seconds' in df.columns:
        seen_speakers = set()
        for i, row in df.iterrows():
            if pd.notna(row['Name']) and pd.notna(row['Seconds']):
                if row['Name'] not in seen_speakers:
                    seen_speakers.add(row['Name'])
                    speaker_data.append({
                        'name': row['Name'],
                        'seconds': int(row['Seconds']),
                        'time_str': seconds_to_time_str(row['Seconds']),
                        'row_index': i  # Add row index for reference
                    })
    else:
        raise ValueError("Excel file doesn't contain the expected columns (Name/Seconds or First/First_Seconds)")
    
    # Sort by timestamp
    speaker_data.sort(key=lambda x: x['seconds'])
    return speaker_data

# -------------------------------------------------------------
# Batch Processing Utilities
# -------------------------------------------------------------

def create_time_batches(transcript_data, batch_size_minutes=DEFAULT_BATCH_SIZE_MINUTES):
    """
    Create time-based batches directly from transcript data
    
    Args:
        transcript_data (list): List of transcript entries
        batch_size_minutes (int): Batch size in minutes
        
    Returns:
        list: List of batches, each containing transcript entries
    """
    if not transcript_data:
        return []
    
    # Get start and end time of the meeting
    start_time = transcript_data[0]['seconds']
    
    # Determine end time - either from explicit end_seconds or last entry plus buffer
    if 'end_seconds' in transcript_data[-1]:
        end_time = transcript_data[-1]['end_seconds']
    else:
        end_time = transcript_data[-1]['seconds'] + 60  # Add a small buffer
    
    # Convert batch size to seconds
    batch_size_seconds = batch_size_minutes * 60
    
    # Calculate total duration
    total_duration = end_time - start_time
    
    # For short meetings (less than batch size), create a single batch
    if total_duration <= batch_size_seconds:
        return [transcript_data]
    
    # For longer meetings, create time-based batches
    batches = []
    batch_start = start_time
    
    while batch_start < end_time:
        batch_end = min(batch_start + batch_size_seconds, end_time)
        
        # Get entries for this time range
        batch_entries = [
            entry for entry in transcript_data
            if batch_start <= entry['seconds'] < batch_end
        ]
        
        # Only add non-empty batches
        if batch_entries:
            batches.append(batch_entries)
        
        # Move to next batch
        batch_start = batch_end
    
    return batches

def extract_text_for_batch(batch_entries):
    """
    Extract transcript text for a batch of entries
    
    Args:
        batch_entries (list): List of transcript entries for the batch
        
    Returns:
        str: Concatenated text for the batch
    """
    batch_text = ""
    
    # Sort by timestamp
    sorted_entries = sorted(batch_entries, key=lambda x: x['seconds'])
    
    # Concatenate text from all entries
    for entry in sorted_entries:
        batch_text += f"{entry['name']}: {entry['text']}\n\n"
    
    return batch_text

# -------------------------------------------------------------
# Topic Extraction and Matching
# -------------------------------------------------------------

def find_best_timestamp_match(topic_content, speaker_name, transcript_data):
    """
    Find the best timestamp match for a topic in the transcript
    
    Args:
        topic_content (str): Content text of the topic
        speaker_name (str): Name of the speaker
        transcript_data (list): List of transcript entries
        
    Returns:
        dict: The best matching transcript entry
    """
    # First, filter by speaker
    speaker_entries = [entry for entry in transcript_data if entry['name'] == speaker_name]
    
    if not speaker_entries:
        return None
    
    # Try to import the refineStartTimes module
    try:
        module_name = "refineStartTimes"
        if module_name in sys.modules:
            refine_module = sys.modules[module_name]
        else:
            # Look for the module in the current directory
            module_path = os.path.join(os.path.dirname(__file__), "refineStartTimes.py")
            if os.path.exists(module_path):
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                refine_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(refine_module)
            else:
                raise ImportError("refineStartTimes.py not found")
        
        # Use the advanced matching algorithm from refineStartTimes
        if hasattr(refine_module, 'find_best_timestamp_match'):
            return refine_module.find_best_timestamp_match(topic_content, speaker_name, speaker_entries)
    except Exception as e:
        # Fall back to basic matching if import fails
        print(f"Warning: Could not use refineStartTimes for matching: {e}")
    
    # Basic matching (fallback)
    # First check if any entry has matching topic information
    topic_entries = [entry for entry in speaker_entries if 
                    'topic' in entry and entry['topic'] is not None]
    
    if topic_entries:
        # Return the first entry with topic information
        return topic_entries[0]
    
    # If no topic entries found, use basic text similarity matching
    # Use a very simple approach - look for keyword overlap
    topic_words = set(topic_content.lower().split())
    best_match = None
    highest_score = 0
    
    for entry in speaker_entries:
        entry_words = set(entry['text'].lower().split())
        # Calculate word overlap
        overlap = len(topic_words & entry_words)
        # Normalize by the length of the shorter text
        score = overlap / min(len(topic_words), len(entry_words)) if min(len(topic_words), len(entry_words)) > 0 else 0
        
        if score > highest_score:
            highest_score = score
            best_match = entry
    
    # If we found a decent match, return it
    if best_match and highest_score > 0.1:
        return best_match
    
    # Default: return the first entry for this speaker
    return speaker_entries[0]

def extract_topics_from_summary(summary, video_id=None, transcript_data=None):
    """
    Extract individual topics from a batch summary.
    Looks for bold titles in the format: **Topic Title - Speaker Name** (H:MM:SS)
    Returns a list of dictionaries with topic, speaker, timestamp, and content info.
    
    Args:
        summary (str): The batch summary text
        video_id (str, optional): Panopto video ID for creating direct links (can be None)
        transcript_data (list, optional): Transcript data for better timestamp matching
        
    Returns:
        list: List of topic dictionaries
    """
    # Updated pattern to match: **Topic - Speaker** (H:MM:SS): followed by text
    # This captures the timestamp if present
    pattern = r'\*\*(.+?)\s+-\s+(.+?)\*\*\s*(?:\((\d+:\d{2}:\d{2})\))?\s*:' 
    
    # Find all matches in the summary
    topic_matches = list(re.finditer(pattern, summary))
    
    topics = []
    
    for idx, match in enumerate(topic_matches):
        topic = match.group(1).strip()
        # Keep only the first speaker if multiple are present
        speaker_raw = match.group(2).strip()
        speaker = speaker_raw
        
        # Get timestamp if present
        timestamp = match.group(3)
        timestamp_seconds = None
        video_link = None
        
        # Convert timestamp to seconds if present
        if timestamp:
            timestamp_seconds = time_str_to_seconds(timestamp)
            
            # If transcript data is provided, try to find a better timestamp match for this topic/speaker
            if transcript_data:
                start_pos = match.end()
                # Determine end of content: either next match or end of summary
                next_start = topic_matches[idx + 1].start() if idx + 1 < len(topic_matches) else len(summary)
                topic_content = summary[start_pos:next_start].strip()
                
                # Find the best matching entry for this topic/speaker
                best_match = find_best_timestamp_match(topic_content, speaker, transcript_data)
                if best_match:
                    # Use the matched timestamp instead
                    timestamp_seconds = best_match.get('matched_seconds', best_match.get('seconds', timestamp_seconds))
            
            # Create the video link only if video_id is provided
            if video_id and timestamp_seconds is not None:
                video_link = f'https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id={video_id}&start={timestamp_seconds}'
        
        start_pos = match.start()
        end_pos = match.end()
        
        # Determine end of content: either next match or end of summary
        next_start = topic_matches[idx + 1].start() if idx + 1 < len(topic_matches) else len(summary)
        
        content = summary[end_pos:next_start].strip()
        
        topics.append({
            'topic': topic,
            'speaker': speaker,
            'timestamp': timestamp,
            'timestamp_seconds': timestamp_seconds,
            'video_link': video_link,  # Will be None if no video_id provided
            'position': start_pos,
            'content': content,
            'full_match': match.group(0)
        })
    
    return topics

def update_speaker_timestamps_for_topics(topics, transcript_data):
    """
    Update topic timestamps to better match the actual content
    
    Args:
        topics (list): List of topic dictionaries extracted from summaries
        transcript_data (list): List of transcript entries for matching
        
    Returns:
        list: Updated list of topic dictionaries
    """
    for topic in topics:
        speaker = topic['speaker']
        content = topic['content']
        
        # Find the best matching entry for this topic/speaker
        best_match = find_best_timestamp_match(content, speaker, transcript_data)
        
        if best_match:
            # Update the timestamp to the matched entry
            matched_seconds = best_match.get('matched_seconds', best_match.get('seconds'))
            matched_time_str = best_match.get('matched_time_str', 
                                             seconds_to_time_str(matched_seconds))
            
            # Only update if this is different from the original
            if topic['timestamp_seconds'] != matched_seconds:
                print(f"Updated timestamp for topic '{topic['topic']}' by {speaker} from " 
                      f"{topic['timestamp']} to {matched_time_str}")
                
                topic['timestamp_seconds'] = matched_seconds
                topic['timestamp'] = matched_time_str
                
                # Update the video link as well if video_link exists and we can extract video_id
                if topic.get('video_link'):
                    video_id_match = re.search(r'id=([^&]+)', topic['video_link'])
                    if video_id_match:
                        video_id = video_id_match.group(1)
                        topic['video_link'] = f'https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id={video_id}&start={matched_seconds}'
    
    return topics
# -------------------------------------------------------------
# OpenAI API Utilities
# -------------------------------------------------------------

def get_api_key():
    """
    Get OpenAI API key from constant, environment variable, or config file
    
    Returns:
        str: OpenAI API key
    """
    # Check the constant first
    api_key = OPENAI_API_KEY
    
    # Then try environment variable if constant is empty
    if not api_key:
        api_key = os.environ.get('OPENAI_API_KEY')
    
    # Then check for config file in user's home directory
    if not api_key:
        config_path = os.path.expanduser('~/.openai_config')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    api_key = config.get('api_key')
            except Exception:
                pass
    
    # If still no API key, prompt user
    if not api_key:
        print("OpenAI API key not found. Please enter your API key:")
        api_key = input("> ").strip()
        
        if api_key:
            # Save for future use (optional)
            try:
                if input("Save API key for future use? (y/n): ").lower() == 'y':
                    os.makedirs(os.path.dirname(config_path), exist_ok=True)
                    with open(config_path, 'w') as f:
                        json.dump({'api_key': api_key}, f)
                    os.chmod(config_path, 0o600)  # Restrict permissions
            except Exception as e:
                print(f"Error saving API key: {e}")
    
    return api_key