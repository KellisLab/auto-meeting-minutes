import os
import re
import sys
import pandas as pd
import numpy as np
import importlib.util
import json
from dotenv import load_dotenv
from typing import List, Dict
import warnings
warnings.filterwarnings('ignore')

# Load environment variables from .env file
load_dotenv(override=True)

# Constants
OPENAI_API_KEY = os.getenv("API_KEY")
DEFAULT_MODEL = os.getenv("GPT_MODEL", "gpt-4o")
DEFAULT_BATCH_SIZE_MINUTES = 25

from embedding_model import train_embedding_model, extract_sentence_embeddings

# -------------------------------------------------------------
# Text Utilities
# -------------------------------------------------------------

def sanitize_filename(name):
    """Sanitize meeting name to create a valid filename"""
    # Replace colons with dots (e.g., "4:00pm" → "4.00pm")
    name = re.sub(r':', '.', name)
    # Replace invalid filename characters with underscores
    name = re.sub(r'[\\/*?"<>|]', '_', name)
    # Replace multiple spaces with a single underscore
    name = re.sub(r'\s+', '_', name)
    # Limit filename length
    if len(name) > 100:
        name = name[:100]
    return name

def parse_json(summary_text):
    import json
    # Remove markdown code blocks if present
    json_text = summary_text
    if "```json" in json_text:
        json_text = json_text.split("```json")[1].split("```")[0].strip()
    elif "```" in json_text:
        json_text = json_text.split("```")[1].split("```")[0].strip()
    # Parse the JSON
    try:
        data = json.loads(json_text)
        results = data.get("results", {})
    except json.JSONDecodeError as e:
        return f"Error parsing JSON response: {str(e)}"
    # 3. Construct the list of lines in the format: **<Topic_Title> - <Speaker_Name>, ..., <Speaker_Name>** (H:MM:SS): <Summary_Content>
    formatted_lines = []
    for topic_title, topic_data in results.items():
        speakers = topic_data.get("speakers", [])
        timestamp = topic_data.get("timestamp", "")
        summary = topic_data.get("summary", "")
        # Format speaker names
        speaker_str = ", ".join(speakers)
        # Construct the formatted line
        line = f"**{topic_title} - {speaker_str}** {timestamp}: {summary}"
        formatted_lines.append(line)
    # Join all lines with newlines
    return "\n\n".join(formatted_lines)
    
# -------------------------------------------------------------
# Information-Theoretic Utilities
# -------------------------------------------------------------

def calculate_entropy(embedding_matrix):
    """
    Calculate entropy of an embedding matrix
    
    Args:
        embedding_matrix: (n_words, emb_dim) word embeddings for a sentence
    
    Returns:
        float: Entropy value
    """
    # Normalize to probability distribution
    norms = np.linalg.norm(embedding_matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1  # Avoid division by zero
    probs = norms / norms.sum()
    
    # Calculate entropy: -sum(p * log(p))
    probs = probs.flatten()
    probs = probs[probs > 0]  # Remove zeros
    entropy = -np.sum(probs * np.log(probs + 1e-10))
    
    return entropy


def calculate_mutual_information(emb1, emb2):
    """
    Calculate mutual information between two sentence embeddings
    
    MI(X;Y) = H(X) + H(Y) - H(X,Y)
    
    Where high MI = sentences share information (same topic)
          low MI = sentences are independent (topic boundary)
    
    Args:
        emb1: (n_words1, emb_dim) first sentence embedding
        emb2: (n_words2, emb_dim) second sentence embedding
    
    Returns:
        float: Mutual information score
    """
    # Individual entropies
    h_x = calculate_entropy(emb1)
    h_y = calculate_entropy(emb2)
    
    # Joint entropy (concatenate embeddings)
    joint = np.vstack([emb1, emb2])
    h_xy = calculate_entropy(joint)
    
    # Mutual information
    mi = h_x + h_y - h_xy
    
    return mi


def calculate_cosine_similarity_score(emb1, emb2):
    """
    Calculate cosine similarity between average sentence embeddings
    
    Args:
        emb1: (n_words1, emb_dim) first sentence embedding
        emb2: (n_words2, emb_dim) second sentence embedding
    
    Returns:
        float: Cosine similarity score
    """
    from sklearn.metrics.pairwise import cosine_similarity
    
    # Average pooling
    avg1 = emb1.mean(axis=0).reshape(1, -1)
    avg2 = emb2.mean(axis=0).reshape(1, -1)
    
    # Cosine similarity
    similarity = cosine_similarity(avg1, avg2)[0, 0]
    
    return similarity

# -------------------------------------------------------------
# Information-Theoretic Batching with NN Embeddings
# -------------------------------------------------------------

def calculate_information_content_nn(transcript_data, sentence_embeddings):
    """
    Calculate information content using NN-extracted embeddings
    
    Args:
        transcript_data: List of transcript entry dicts
        sentence_embeddings: List of embedding matrices from NN
    
    Returns:
        info_drops: Array of information drop scores
        mi_scores: Array of mutual information scores
    """
    n = len(transcript_data)
    mi_scores = np.zeros(n - 1)
    
    print("Calculating mutual information between consecutive sentences...")
    
    # Calculate MI between consecutive sentences
    for i in range(n - 1):
        emb1 = sentence_embeddings[i]
        emb2 = sentence_embeddings[i + 1]
        
        # Calculate mutual information
        mi = calculate_mutual_information(emb1, emb2)
        
        # Also consider cosine similarity for robustness
        cos_sim = calculate_cosine_similarity_score(emb1, emb2)
        
        # Combined score (higher = more related)
        combined_score = 0.7 * mi + 0.3 * cos_sim
        mi_scores[i] = combined_score
    
    # Normalize to [0, 1]
    if mi_scores.max() > mi_scores.min():
        mi_scores = (mi_scores - mi_scores.min()) / (mi_scores.max() - mi_scores.min())
    
    # Information content drops at boundaries
    # Take derivative to find where MI drops sharply
    info_drops = np.zeros(n)
    info_drops[1:-1] = mi_scores[:-1] - mi_scores[1:]  # Negative derivative
    
    return info_drops, mi_scores


def create_information_batches(
    transcript_data: List[Dict],
    target_batch_size_minutes: int = 25,
    min_batch_size: int = 10,
    boundary_threshold: float = 0.3,
    emb_size: int = 128,
    epochs: int = 10,
    cnn_kernel_sizes: List[int] = [3, 5, 7]
) -> List[List[Dict]]:
    """
    Create batches using CNN+Attention NN embeddings + information theory
    
    Algorithm:
    1. Train CNN+Attention embedding model on transcript (self-supervised)
    2. Extract CNN-enhanced learned embeddings for each sentence
    3. Calculate mutual information between consecutive sentences
    4. Find boundaries where MI drops significantly
    5. Create batches at natural topic boundaries
    
    Args:
        transcript_data: List of transcript entries
        target_batch_size_minutes: Target batch size in minutes
        min_batch_size: Minimum entries per batch
        boundary_threshold: Threshold for detecting boundaries (higher = fewer splits)
        emb_size: Embedding dimension for NN
        epochs: Training epochs for NN
        cnn_kernel_sizes: List of CNN kernel sizes (e.g., [3,5,7] for 3-5-7 grams)
    
    Returns:
        List of batches
    """
    if not transcript_data:
        return []
    
    if len(transcript_data) < min_batch_size:
        return [transcript_data]
    
    # Step 1: Train CNN+Attention embedding model
    model = train_embedding_model(
        transcript_data, 
        emb_size=emb_size, 
        epochs=15,
        cnn_kernel_sizes=cnn_kernel_sizes
    )
    
    # Step 2: Extract CNN-enhanced embeddings
    sentence_embeddings = extract_sentence_embeddings(transcript_data, model, use_cnn=True)
    
    # Step 3: Calculate information content
    info_drops, mi_scores = calculate_information_content_nn(transcript_data, sentence_embeddings)
    
    # Step 4: Find potential boundaries
    potential_boundaries = []
    for i in range(1, len(info_drops) - 1):
        if info_drops[i] > boundary_threshold:
            potential_boundaries.append(i)
    
    potential_boundaries_set = set(potential_boundaries)
    print(f"Found {len(potential_boundaries)} potential topic boundaries")
    
    # Step 5: Create batches
    target_batch_seconds = target_batch_size_minutes * 60
    start_time = transcript_data[0]['seconds']
    
    batches = []
    current_batch = []
    batch_start_time = start_time
    
    for i, entry in enumerate(transcript_data):
        current_batch.append(entry)
        
        # Calculate current batch duration
        batch_duration = entry['seconds'] - batch_start_time
        
        should_split = False
        
        # Decision criteria:
        # 1. We've reached target duration AND current index is a boundary
        if batch_duration >= target_batch_seconds and len(current_batch) >= min_batch_size:
            # Only split if we are exactly at a boundary
            if i in potential_boundaries_set:
                should_split = True
        
        # 2. Significantly exceeded target AND at a speaker change
        elif batch_duration >= target_batch_seconds * 1.5 and len(current_batch) >= min_batch_size:
            if i + 1 < len(transcript_data) and entry['name'] != transcript_data[i + 1]['name']:
                should_split = True
        
        # 3. Very long batch (force split)
        elif len(current_batch) >= 100:
            should_split = True
        
        if should_split:
            batches.append(current_batch)
            start = seconds_to_time_str(current_batch[0]['seconds'])
            end = seconds_to_time_str(current_batch[-1]['seconds'])
            duration = (current_batch[-1]['seconds'] - current_batch[0]['seconds']) / 60
            
            # Calculate average MI for this batch
            batch_start_idx = len(batches) - 1
            if i > 0 and i < len(mi_scores):
                # Get MI scores for this batch
                batch_mi_indices = [j for j in range(len(mi_scores)) if j < i and j >= i - len(current_batch)]
                if batch_mi_indices:
                    avg_mi = np.mean([mi_scores[j] for j in batch_mi_indices])
                    print(f"Batch {len(batches)}: {len(current_batch)} entries, "
                          f"{start} - {end} ({duration:.1f}min), avg_MI={avg_mi:.3f}")
                else:
                    print(f"Batch {len(batches)}: {len(current_batch)} entries, "
                          f"{start} - {end} ({duration:.1f}min)")
            
            current_batch = []
            if i + 1 < len(transcript_data):
                batch_start_time = transcript_data[i + 1]['seconds']
    
    # Add remaining entries
    if current_batch:
        batches.append(current_batch)
        start = seconds_to_time_str(current_batch[0]['seconds'])
        end = seconds_to_time_str(current_batch[-1]['seconds'])
        duration = (current_batch[-1]['seconds'] - current_batch[0]['seconds']) / 60
        print(f"Final batch {len(batches)}: {len(current_batch)} entries, "
              f"{start} - {end} ({duration:.1f}min)")
    
    print(f"Created {len(batches)} CNN+Attention+MI-based batches")
    print("=" * 60)
    
    return batches

# -------------------------------------------------------------
# Traditional Time-Based Batching
# -------------------------------------------------------------

def create_time_batches_traditional(
    transcript_data: List[Dict],
    batch_size_minutes: int = DEFAULT_BATCH_SIZE_MINUTES
) -> List[List[Dict]]:
    """
    Create time-based batches (traditional approach)
    
    Args:
        transcript_data: List of transcript entries
        batch_size_minutes: Batch size in minutes
        
    Returns:
        List of batches, each containing transcript entries
    """
    if not transcript_data:
        return []
    
    # Get start and end time of the meeting
    start_time = transcript_data[0]['seconds']
    
    # Determine end time
    if 'end_seconds' in transcript_data[-1]:
        end_time = transcript_data[-1]['end_seconds']
    else:
        end_time = transcript_data[-1]['seconds']
    
    # Convert batch size to seconds
    batch_size_seconds = batch_size_minutes * 60
    
    # Calculate total duration
    total_duration = end_time - start_time
    
    # For short meetings, create a single batch
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
            print(f"Created time-based batch {len(batches)}: {len(batch_entries)} entries, "
                  f"{seconds_to_time_str(batch_start)} - {seconds_to_time_str(batch_end)}")
        
        # Move to next batch
        batch_start = batch_end
    
    return batches


# -------------------------------------------------------------
# Unified Batch Creation Interface
# -------------------------------------------------------------

def create_time_batches(
    transcript_data: List[Dict],
    batch_size_minutes: int = DEFAULT_BATCH_SIZE_MINUTES,
    use_smart_batching: bool = True
) -> List[List[Dict]]:
    """
    Create batches - either time-based or NN+information-theoretic
    
    This is the main entry point for batch creation.
    Set use_smart_batching=True to enable NN-based segmentation.
    
    Args:
        transcript_data: List of transcript entries
        batch_size_minutes: Target batch size in minutes
        use_smart_batching: Whether to use NN+information-theoretic batching
        
    Returns:
        List of batches, each containing transcript entries
    """
    
    if use_smart_batching:
        try:
            # Use NN + information-theoretic approach
            batches = create_information_batches(
                transcript_data,
                target_batch_size_minutes=batch_size_minutes,
                min_batch_size=10,
                boundary_threshold=0.15,
                emb_size=256,
                epochs=20
            )
            return batches
            
        except Exception as e:
            print(f"Warning: NN+information-theoretic batching failed: {e}")
            print("Falling back to time-based batching...")
            import traceback
            traceback.print_exc()
    
    # Fallback to traditional time-based batching
    print("=" * 60)
    print("Using TIME-BASED BATCHING")
    print("=" * 60)
    batches = create_time_batches_traditional(transcript_data, batch_size_minutes)
    print(f"Created {len(batches)} time-based batches")
    print("=" * 60)
    
    return batches


# -------------------------------------------------------------
# Time and Timestamp Utilities
# -------------------------------------------------------------

def seconds_to_time_str(seconds):
    """Convert seconds to H:MM:SS format"""
    if pd.isna(seconds):
        return "00:00:00"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"

def time_str_to_seconds(time_str):
    """Convert H:MM:SS time string to seconds"""
    parts = time_str.split(':')
    if len(parts) == 3:
        hours, minutes, seconds = map(int, parts)
        return hours * 3600 + minutes * 60 + seconds
    return 0

def format_corrected_timestamp(seconds):
    """Convert seconds to corrected timestamp string"""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"

def verify_timestamp_format(timestamp_str, seconds):
    """Verify timestamp matches seconds value"""
    try:
        parts = timestamp_str.split(':')
        if len(parts) == 3:
            hours, minutes, secs = map(int, parts)
            ts_seconds = hours * 3600 + minutes * 60 + secs
            if ts_seconds != seconds:
                return format_corrected_timestamp(seconds)
    except:
        return format_corrected_timestamp(seconds)
    return timestamp_str

# -------------------------------------------------------------
# Data Extraction and Processing Utilities
# -------------------------------------------------------------

def get_column_letter(col_idx):
    """Convert column index to letter"""
    letter = ''
    while col_idx > 0:
        col_idx, remainder = divmod(col_idx - 1, 26)
        letter = chr(65 + remainder) + letter
    return letter

def extract_transcript_data(df):
    """Extract transcript data from DataFrame"""
    transcript_data = []
    
    if 'Name' in df.columns and 'Seconds' in df.columns and 'Text' in df.columns:
        for i, row in df.iterrows():
            if pd.notna(row['Name']) and pd.notna(row['Seconds']) and pd.notna(row['Text']):
                entry = {
                    'name': row['Name'],
                    'seconds': int(row['Seconds']),
                    'time_str': seconds_to_time_str(row['Seconds']),
                    'text': row['Text'],
                    'row_index': i
                }
                
                if 'End_Seconds' in df.columns and pd.notna(row['End_Seconds']):
                    entry['end_seconds'] = int(row['End_Seconds'])
                    entry['end_time_str'] = seconds_to_time_str(row['End_Seconds'])
                
                if 'Topic' in df.columns and pd.notna(row['Topic']):
                    entry['topic'] = row['Topic']
                
                if 'Matched_Seconds' in df.columns and pd.notna(row['Matched_Seconds']):
                    entry['matched_seconds'] = int(row['Matched_Seconds'])
                    entry['matched_time_str'] = seconds_to_time_str(row['Matched_Seconds'])
                
                transcript_data.append(entry)
    else:
        raise ValueError("Excel file doesn't contain expected columns (Name, Seconds, Text)")
    
    transcript_data.sort(key=lambda x: x['seconds'])
    return transcript_data

def extract_unique_speakers(df):
    """Extract unique speakers from DataFrame"""
    speaker_data = []
    
    if 'First' in df.columns and 'First_Seconds' in df.columns and df['First'].notna().any():
        unique_speakers = df[df['First'].notna()]
        for i, row in unique_speakers.iterrows():
            if pd.notna(row['First']) and pd.notna(row['First_Seconds']):
                speaker_data.append({
                    'name': row['First'],
                    'seconds': int(row['First_Seconds']),
                    'time_str': seconds_to_time_str(row['First_Seconds']),
                    'row_index': i
                })
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
                        'row_index': i
                    })
    else:
        raise ValueError("Excel file doesn't contain expected columns")
    
    speaker_data.sort(key=lambda x: x['seconds'])
    return speaker_data

def extract_text_for_batch(batch_entries):
    """Extract concatenated text for batch"""
    batch_text = ""
    sorted_entries = sorted(batch_entries, key=lambda x: x['seconds'])
    for entry in sorted_entries:
        batch_text += f"{entry['name']}: {entry['text']}\n\n"
    return batch_text

# -------------------------------------------------------------
# Topic Extraction (keeping existing functions)
# -------------------------------------------------------------

def find_best_timestamp_match(topic_content, speaker_name, transcript_data):
    """Find best timestamp match for topic"""
    speaker_entries = [entry for entry in transcript_data if entry['name'] == speaker_name]
    if not speaker_entries:
        return None
    
    try:
        module_name = "refineStartTimes"
        if module_name in sys.modules:
            refine_module = sys.modules[module_name]
        else:
            module_path = os.path.join(os.path.dirname(__file__), "refineStartTimes.py")
            if os.path.exists(module_path):
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                refine_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(refine_module)
            else:
                raise ImportError("refineStartTimes.py not found")
        
        if hasattr(refine_module, 'find_best_timestamp_match'):
            return refine_module.find_best_timestamp_match(topic_content, speaker_name, speaker_entries)
    except Exception as e:
        print(f"Warning: Could not use refineStartTimes: {e}")
    
    topic_entries = [entry for entry in speaker_entries if 'topic' in entry and entry['topic'] is not None]
    if topic_entries:
        return topic_entries[0]
    
    topic_words = set(topic_content.lower().split())
    best_match = None
    highest_score = 0
    
    for entry in speaker_entries:
        entry_words = set(entry['text'].lower().split())
        overlap = len(topic_words & entry_words)
        score = overlap / min(len(topic_words), len(entry_words)) if min(len(topic_words), len(entry_words)) > 0 else 0
        
        if score > highest_score:
            highest_score = score
            best_match = entry
    
    if best_match and highest_score > 0.1:
        return best_match
    
    return speaker_entries[0]

def extract_topics_from_summary(summary, video_id=None, transcript_data=None):
    """Extract topics from batch summary"""
    pattern = r'\*\*(.+?)\s+-\s+(.+?)\*\*\s*(?:\((\d+:\d{2}:\d{2})\))?\s*:' 
    topic_matches = list(re.finditer(pattern, summary))
    topics = []
    
    for idx, match in enumerate(topic_matches):
        topic = match.group(1).strip()
        speaker = match.group(2).strip()
        timestamp = match.group(3)
        timestamp_seconds = None
        video_link = None
        
        if timestamp:
            timestamp_seconds = time_str_to_seconds(timestamp)
            
            if transcript_data:
                start_pos = match.end()
                next_start = topic_matches[idx + 1].start() if idx + 1 < len(topic_matches) else len(summary)
                topic_content = summary[start_pos:next_start].strip()
                
                best_match = find_best_timestamp_match(topic_content, speaker, transcript_data)
                if best_match:
                    timestamp_seconds = best_match.get('matched_seconds', best_match.get('seconds', timestamp_seconds))
            
            if video_id and timestamp_seconds is not None:
                video_link = f'https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id={video_id}&start={timestamp_seconds}'
        
        start_pos = match.start()
        end_pos = match.end()
        next_start = topic_matches[idx + 1].start() if idx + 1 < len(topic_matches) else len(summary)
        content = summary[end_pos:next_start].strip()
        
        topics.append({
            'topic': topic,
            'speaker': speaker,
            'timestamp': timestamp,
            'timestamp_seconds': timestamp_seconds,
            'video_link': video_link,
            'position': start_pos,
            'content': content,
            'full_match': match.group(0)
        })
    
    return topics

def update_speaker_timestamps_for_topics(topics, transcript_data):
    """Update topic timestamps"""
    for topic in topics:
        speaker = topic['speaker']
        content = topic['content']
        
        best_match = find_best_timestamp_match(content, speaker, transcript_data)
        
        if best_match:
            matched_seconds = best_match.get('matched_seconds', best_match.get('seconds'))
            matched_time_str = best_match.get('matched_time_str', seconds_to_time_str(matched_seconds))
            
            if topic['timestamp_seconds'] != matched_seconds:
                print(f"Updated timestamp for topic '{topic['topic']}' by {speaker} from {topic['timestamp']} to {matched_time_str}")
                topic['timestamp_seconds'] = matched_seconds
                topic['timestamp'] = matched_time_str
                
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
    """Get OpenAI API key"""
    api_key = OPENAI_API_KEY
    
    if not api_key:
        api_key = os.environ.get('OPENAI_API_KEY')
    
    if not api_key:
        config_path = os.path.expanduser('~/.openai_config')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    api_key = config.get('api_key')
            except Exception:
                pass
    
    if not api_key:
        print("OpenAI API key not found. Please enter your API key:")
        api_key = input("> ").strip()
        
        if api_key:
            try:
                if input("Save API key for future use? (y/n): ").lower() == 'y':
                    os.makedirs(os.path.dirname(config_path), exist_ok=True)
                    with open(config_path, 'w') as f:
                        json.dump({'api_key': api_key}, f)
                    os.chmod(config_path, 0o600)
            except Exception as e:
                print(f"Error saving API key: {e}")
    
    return api_key