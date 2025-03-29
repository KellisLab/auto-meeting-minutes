#!/usr/bin/env python3
"""
refineStartTimes.py - Refine start times for speaker segments in transcript files

This script addresses the issue where the same speaker appears multiple times in a meeting,
but topics in the meeting summary are only linked to their first occurrence. The script:

1. Analyzes text content to better match topics with the correct timestamp instances
2. Updates the timestamp mapping in the Excel file to include topic-based matching
3. Can be used standalone or integrated into the full processing pipeline

Usage:
    python refineStartTimes.py input.xlsx [output.xlsx]

Example:
    python refineStartTimes.py meeting.xlsx refined_meeting.xlsx
"""

import sys
import os
import pandas as pd
import re
import argparse
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords

# Ensure NLTK resources are available
def download_nltk_resources():
    """Download necessary NLTK resources if not already present"""
    try:
        # Test if resources are available
        stopwords.words('english')
        word_tokenize("Test sentence")
        sent_tokenize("Test sentence. Another sentence.")
    except:
        # Download if not available
        print("Downloading required NLTK resources...")
        nltk.download('punkt')
        nltk.download('stopwords')
        print("Download complete.")

# Helper functions for text processing
def preprocess_text(text):
    """Preprocess text for better matching"""
    if not isinstance(text, str):
        return ""
    
    # Convert to lowercase and remove non-alphanumeric characters
    text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text.lower())
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def extract_keywords(text, top_n=10):
    """Extract top keywords from text"""
    if not text or not isinstance(text, str):
        return []
    
    # Tokenize and filter stop words
    stop_words = set(stopwords.words('english'))
    words = word_tokenize(text.lower())
    words = [word for word in words if word.isalnum() and word not in stop_words]
    
    # Get frequency distribution
    word_freq = {}
    for word in words:
        word_freq[word] = word_freq.get(word, 0) + 1
    
    # Get top n words by frequency
    top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [word for word, _ in top_words]

def compute_text_similarity(text1, text2):
    """Compute cosine similarity between two text strings"""
    if not text1 or not text2:
        return 0.0
        
    # Create a TF-IDF vectorizer
    vectorizer = TfidfVectorizer()
    
    try:
        # Transform texts to vectors
        tfidf_matrix = vectorizer.fit_transform([text1, text2])
        
        # Compute cosine similarity
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        return similarity
    except:
        # Fallback if vectorization fails
        return 0.0

def find_best_timestamp_match(topic_text, speaker, transcript_entries, max_time_gap=1800):
    """
    Find the best timestamp match for a topic based on text similarity
    
    Args:
        topic_text (str): The text of the topic to match
        speaker (str): The speaker name
        transcript_entries (list): List of transcript entries for matching
        max_time_gap (int): Maximum time gap in seconds to consider (default: 30 minutes)
        
    Returns:
        dict: The best matching entry with timestamp information
    """
    # Filter entries for the specified speaker
    speaker_entries = [entry for entry in transcript_entries if entry['name'] == speaker]
    
    if not speaker_entries:
        return None
    
    # Process the topic text
    processed_topic = preprocess_text(topic_text)
    topic_keywords = extract_keywords(processed_topic)
    
    # If no meaningful keywords were extracted, return the first entry for the speaker
    if not topic_keywords:
        return speaker_entries[0]
    
    # Calculate similarity scores for each entry
    best_match = None
    highest_score = -1
    
    for entry in speaker_entries:
        # Process entry text
        processed_entry = preprocess_text(entry['text'])
        
        # Skip empty entries
        if not processed_entry:
            continue
        
        # Calculate keyword overlap
        entry_keywords = extract_keywords(processed_entry)
        keyword_overlap = len(set(topic_keywords) & set(entry_keywords))
        
        # Calculate text similarity
        similarity = compute_text_similarity(processed_topic, processed_entry)
        
        # Combined score (weighted more towards similarity)
        score = (0.7 * similarity) + (0.3 * (keyword_overlap / max(len(topic_keywords), 1)))
        
        # Update best match if score is higher
        if score > highest_score:
            highest_score = score
            best_match = entry
    
    # If no good match was found, return the first entry
    if best_match is None or highest_score < 0.1:
        return speaker_entries[0]
    
    return best_match

def refine_start_times(xlsx_file, output_file=None):
    """
    Refine start times for topics in the Excel file
    
    Args:
        xlsx_file (str): Path to input Excel file
        output_file (str, optional): Path to output Excel file
        
    Returns:
        str: Path to the refined Excel file
    """
    if output_file is None:
        base_name = os.path.splitext(xlsx_file)[0]
        output_file = f"{base_name}_refined.xlsx"
    
    # Load the Excel file
    df = pd.read_excel(xlsx_file)
    
    # Extract transcript entries
    transcript_entries = []
    
    if 'Name' in df.columns and 'Seconds' in df.columns and 'Text' in df.columns:
        for i, row in df.iterrows():
            if pd.notna(row['Name']) and pd.notna(row['Seconds']) and pd.notna(row['Text']):
                entry = {
                    'name': row['Name'],
                    'seconds': int(row['Seconds']),
                    'time_str': row['Time'] if 'Time' in df.columns else None,
                    'text': row['Text'],
                    'row_index': i  # Keep track of the row index for updating
                }
                transcript_entries.append(entry)
    else:
        raise ValueError("Excel file doesn't contain the expected columns (Name, Seconds, Text)")
    
    # Check if the file has "Topic" and "Topic_Text" columns
    if 'Topic' in df.columns and 'Topic_Text' in df.columns:
        # File already has topic columns, refine timestamps for topics
        topic_rows = df[df['Topic'].notna()].index
        
        print(f"Found {len(topic_rows)} topics in the Excel file. Refining timestamps...")
        
        # Convert columns to object dtype if they're numeric
        for col in ['Topic', 'Topic_Text']:
            if col in df.columns and pd.api.types.is_numeric_dtype(df[col].dtype):
                df[col] = df[col].astype('object')
        
        # Process each topic
        for idx in topic_rows:
            topic = df.loc[idx, 'Topic']
            speaker = df.loc[idx, 'Name']
            topic_text = df.loc[idx, 'Topic_Text']
            
            # Find the best matching entry for this topic
            best_match = find_best_timestamp_match(topic_text, speaker, transcript_entries)
            
            if best_match:
                # Update the timestamp for this topic
                df.loc[idx, 'Seconds'] = best_match['seconds']
                if 'Time' in df.columns and best_match['time_str']:
                    df.loc[idx, 'Time'] = best_match['time_str']
    else:
        # Add metadata columns if they don't exist
        print("Adding topic metadata columns to the Excel file...")
        
        if 'Topic' not in df.columns:
            df['Topic'] = None
        
        if 'Topic_Text' not in df.columns:
            df['Topic_Text'] = None
        
        # Add Matched_Seconds and Original_Seconds columns
        if 'Original_Seconds' not in df.columns:
            df['Original_Seconds'] = df['Seconds']
        
        if 'Matched_Seconds' not in df.columns:
            df['Matched_Seconds'] = None
        
        # Convert columns to object dtype if they're numeric
        for col in ['Topic', 'Topic_Text']:
            if col in df.columns and pd.api.types.is_numeric_dtype(df[col].dtype):
                df[col] = df[col].astype('object')
    
    # Save the refined Excel file
    df.to_excel(output_file, index=False)
    print(f"Refined Excel file saved as: {output_file}")
    
    return output_file

def verify_and_fix_timestamps(markdown_file, output_file=None):
    """
    Verify that displayed timestamps match the seconds in the URLs.
    If they don't match, replace the displayed timestamp with the correct one.
    
    Args:
        markdown_file (str): Path to the markdown file
        output_file (str, optional): Path to the output file
        
    Returns:
        str: Path to the corrected markdown file
    """
    if output_file is None:
        base_name = os.path.splitext(markdown_file)[0]
        output_file = f"{base_name}_corrected.md"
    
    try:
        # Read the markdown file
        with open(markdown_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Pattern to find timestamps with links
        # Captures: 
        # 1. The displayed timestamp [(H:MM:SS)]
        # 2. The URL with seconds parameter
        pattern = r'\[\((\d+:\d{2}:\d{2})\)\]\((https://[^&]+&start=(\d+))\)'
        
        # Find all matches
        matches = list(re.finditer(pattern, content))
        
        corrections_made = 0
        
        # Process each match
        for match in matches:
            displayed_timestamp = match.group(1)  # H:MM:SS
            url = match.group(2)  # Full URL
            url_seconds = int(match.group(3))  # Seconds parameter from URL
            
            # Convert displayed timestamp to seconds
            time_parts = displayed_timestamp.split(':')
            displayed_seconds = (int(time_parts[0]) * 3600) + (int(time_parts[1]) * 60) + int(time_parts[2])
            
            # If there's a mismatch
            if displayed_seconds != url_seconds:
                # Convert URL seconds to H:MM:SS format
                hours, remainder = divmod(url_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                correct_timestamp = f"{hours}:{minutes:02d}:{seconds:02d}"
                
                # Create the corrected format
                original = f"[({displayed_timestamp})]({url})"
                corrected = f"[({correct_timestamp})]({url})"
                
                # Replace in content
                content = content.replace(original, corrected)
                
                corrections_made += 1
                print(f"Corrected timestamp: {displayed_timestamp} → {correct_timestamp} (URL seconds: {url_seconds})")
        
        # Write corrected content to output file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        if corrections_made > 0:
            print(f"Made {corrections_made} timestamp corrections. Saved to: {output_file}")
        else:
            print("No timestamp corrections needed.")
        
        return output_file
    
    except Exception as e:
        print(f"Error verifying timestamps: {e}")
        return None
    
def refine_from_summaries(xlsx_file, summary_md_file, output_file=None):
    """
    Refine start times using information from an existing meeting summary markdown file
    
    Args:
        xlsx_file (str): Path to input Excel file
        summary_md_file (str): Path to meeting summary markdown file
        output_file (str, optional): Path to output Excel file
        
    Returns:
        str: Path to the refined Excel file
    """
    if output_file is None:
        base_name = os.path.splitext(xlsx_file)[0]
        output_file = f"{base_name}_refined_post.xlsx"
    
    # Load the Excel file
    df = pd.read_excel(xlsx_file)
    
    # Extract transcript entries
    transcript_entries = []
    
    if 'Name' in df.columns and 'Seconds' in df.columns and 'Text' in df.columns:
        for i, row in df.iterrows():
            if pd.notna(row['Name']) and pd.notna(row['Seconds']) and pd.notna(row['Text']):
                entry = {
                    'name': row['Name'],
                    'seconds': int(row['Seconds']),
                    'time_str': row['Time'] if 'Time' in df.columns else None,
                    'text': row['Text'],
                    'row_index': i  # Keep track of the row index for updating
                }
                transcript_entries.append(entry)
    else:
        raise ValueError("Excel file doesn't contain the expected columns (Name, Seconds, Text)")
    
    # Read the summary markdown file
    try:
        with open(summary_md_file, 'r', encoding='utf-8') as f:
            summary_text = f.read()
        
        # Extract topics and speakers with timestamps
        # Pattern to match: **Topic - Speaker** [(H:MM:SS)](link)
        # Or: ### Topic - Speaker [(H:MM:SS)](link)
        pattern = r'(?:\*\*|\#\#\#)\s*([^-]+)\s*-\s*([^*#\(\)]+)(?:\*\*)?\s*\[?\(([0-9]+:[0-9]{2}:[0-9]{2})\)\]?'
        
        topic_matches = re.finditer(pattern, summary_text)
        
        # Create a mapping to store topic info
        topics = []
        
        for match in topic_matches:
            topic = match.group(1).strip()
            speaker = match.group(2).strip()
            timestamp = match.group(3).strip()
            
            # Find the content for this topic
            start_pos = match.end()
            end_pos = len(summary_text)
            
            # Try to find the end of this topic's content (next topic or end of file)
            next_topic = re.search(r'(?:\*\*|\#\#\#)\s*[^-]+\s*-\s*[^*#\(\)]+(?:\*\*)?\s*\[?\([0-9]+:[0-9]{2}:[0-9]{2}\)\]?', summary_text[start_pos:])
            if next_topic:
                end_pos = start_pos + next_topic.start()
            
            # Extract the topic content
            content = summary_text[start_pos:end_pos].strip()
            
            topics.append({
                'topic': topic,
                'speaker': speaker,
                'timestamp': timestamp,
                'content': content
            })
        
        print(f"Found {len(topics)} topics in the summary file.")
        
        # Add metadata columns if they don't exist
        if 'Topic' not in df.columns:
            df['Topic'] = None
        
        if 'Topic_Text' not in df.columns:
            df['Topic_Text'] = None
        
        if 'Original_Seconds' not in df.columns:
            df['Original_Seconds'] = df['Seconds'].copy()
        
        if 'Matched_Seconds' not in df.columns:
            df['Matched_Seconds'] = None
        
        # Convert columns to object dtype if they're numeric
        for col in ['Topic', 'Topic_Text']:
            if col in df.columns and pd.api.types.is_numeric_dtype(df[col].dtype):
                df[col] = df[col].astype('object')
        
        # Process each topic
        for topic_info in topics:
            topic = topic_info['topic']
            speaker = topic_info['speaker']
            content = topic_info['content']
            
            # Find the best matching entry for this topic
            best_match = find_best_timestamp_match(content, speaker, transcript_entries)
            
            if best_match:
                # Get the row index for this entry
                row_idx = best_match['row_index']
                
                # Update the metadata for this row
                df.loc[row_idx, 'Topic'] = topic
                df.loc[row_idx, 'Topic_Text'] = content
                df.loc[row_idx, 'Matched_Seconds'] = best_match['seconds']
        
        # Save the refined Excel file
        df.to_excel(output_file, index=False)
        print(f"Refined Excel file saved as: {output_file}")
        
        return output_file
    
    except Exception as e:
        print(f"Error processing summary file: {e}")
        # Fallback to basic refinement
        return refine_start_times(xlsx_file, output_file)

def extract_topics_by_timestamp(summary_md_file):
    """
    Extract topics from summary markdown file and sort by timestamp
    
    Args:
        summary_md_file (str): Path to meeting summary markdown file
        
    Returns:
        list: List of topics sorted by timestamp
    """
    try:
        with open(summary_md_file, 'r', encoding='utf-8') as f:
            summary_text = f.read()
        
        # Extract topics and speakers with timestamps
        # Pattern to match: **Topic - Speaker** [(H:MM:SS)](link)
        # Or: ### Topic - Speaker [(H:MM:SS)](link)
        pattern = r'(?:\*\*|\#\#\#)\s*([^-]+)\s*-\s*([^*#\(\)]+)(?:\*\*)?\s*\[?\(([0-9]+:[0-9]{2}:[0-9]{2})\)\]?'
        
        topic_matches = list(re.finditer(pattern, summary_text))
        
        # Create a list to store topic info
        topics = []
        
        for i, match in enumerate(topic_matches):
            topic = match.group(1).strip()
            speaker = match.group(2).strip()
            timestamp = match.group(3).strip()
            
            # Convert timestamp to seconds for sorting
            time_parts = timestamp.split(':')
            seconds = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + int(time_parts[2])
            
            # Find the content for this topic
            start_pos = match.end()
            end_pos = len(summary_text)
            
            # Try to find the end of this topic's content (next topic or end of file)
            if i < len(topic_matches) - 1:
                end_pos = topic_matches[i+1].start()
            
            # Extract the topic content
            content = summary_text[start_pos:end_pos].strip()
            
            topics.append({
                'topic': topic,
                'speaker': speaker,
                'timestamp': timestamp,
                'seconds': seconds,
                'content': content,
                'match_pos': match.start()
            })
        
        # Sort topics by timestamp in seconds
        topics.sort(key=lambda x: x['seconds'])
        
        return topics
    
    except Exception as e:
        print(f"Error extracting topics by timestamp: {e}")
        return []

def rearrange_summary_by_timestamp(summary_md_file, output_md_file=None):
    """
    Rearrange the meeting summary markdown file to be in chronological order
    with corrected timestamps.
    
    Args:
        summary_md_file (str): Path to meeting summary markdown file
        output_md_file (str, optional): Path to output markdown file
        
    Returns:
        str: Path to the chronologically ordered markdown file
    """
    if output_md_file is None:
        base_name = os.path.splitext(summary_md_file)[0]
        output_md_file = f"{base_name}_chronological.md"
    
    # Extract topics and verify timestamps
    try:
        with open(summary_md_file, 'r', encoding='utf-8') as f:
            original_text = f.read()
        
        # Pattern to match: **Topic - Speaker** [(H:MM:SS)](url&start=seconds)
        pattern = r'(?:\*\*|\#\#\#)\s*([^-]+)\s*-\s*([^*#\(\)]+)(?:\*\*)?\s*\[?\(([0-9]+:[0-9]{2}:[0-9]{2})\)\]?\((https://[^&]+&start=(\d+))[^)]*\)'
        
        topic_matches = list(re.finditer(pattern, original_text))
        
        if not topic_matches:
            print("No topics with timestamps found in the summary file.")
            return None
        
        # Create a list to store topic info
        topics = []
        
        for i, match in enumerate(topic_matches):
            topic = match.group(1).strip()
            speaker = match.group(2).strip()
            displayed_timestamp = match.group(3)  # H:MM:SS format
            url = match.group(4)
            url_seconds = int(match.group(5))
            
            # Convert displayed timestamp to seconds for verification
            parts = displayed_timestamp.split(':')
            displayed_seconds = (int(parts[0]) * 3600) + (int(parts[1]) * 60) + int(parts[2])
            
            # Use URL seconds for sorting (as they are more reliable)
            seconds = url_seconds
            
            # Generate the correct timestamp format from URL seconds
            hours, remainder = divmod(seconds, 3600)
            minutes, secs = divmod(remainder, 60)
            corrected_timestamp = f"{hours}:{minutes:02d}:{secs:02d}"
            
            # Find the content for this topic
            start_pos = match.end()
            end_pos = len(original_text)
            
            # Try to find the end of this topic's content (next topic or end of file)
            if i < len(topic_matches) - 1:
                end_pos = topic_matches[i+1].start()
            
            # Extract the topic content
            content = original_text[start_pos:end_pos].strip()
            
            topics.append({
                'topic': topic,
                'speaker': speaker,
                'displayed_timestamp': displayed_timestamp,
                'corrected_timestamp': corrected_timestamp,
                'url': url, 
                'seconds': seconds,
                'content': content,
                'match': match.group(0)
            })
        
        # Sort topics by the URL seconds (more reliable than displayed timestamps)
        topics.sort(key=lambda x: x['seconds'])
        
        # Extract the header (everything before the first topic)
        header = original_text[:topic_matches[0].start()].strip()
        
        # Generate the new markdown content
        md_lines = [header] if header else ["# Meeting Summaries"]
        
        # Add each topic in chronological order with corrected timestamps
        for topic_info in topics:
            topic = topic_info['topic']
            speaker = topic_info['speaker']
            corrected_timestamp = topic_info['corrected_timestamp']
            url = topic_info['url']
            content = topic_info['content']
            
            # Add the topic heading with corrected timestamp
            md_lines.append(f"\n**{topic} - {speaker}** [({corrected_timestamp})]({url})")
            
            # Add the topic content
            md_lines.append(content)
        
        # Write the file
        with open(output_md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_lines))
        
        print(f"Chronologically ordered markdown with corrected timestamps saved as: {output_md_file}")
        return output_md_file
    
    except Exception as e:
        print(f"Error rearranging summary: {e}")
        return None

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Refine start times for topics in transcript files')
    parser.add_argument('input_file', help='Input Excel file or Markdown file if using --verify-timestamps')
    parser.add_argument('output_file', nargs='?', help='Output file (optional)')
    parser.add_argument('--summary-file', help='Path to meeting summary markdown file (optional)')
    parser.add_argument('--rearrange', action='store_true', help='Rearrange summary file in chronological order')
    parser.add_argument('--chronological-output', help='Path to chronologically ordered markdown file (optional)')
    parser.add_argument('--verify-timestamps', action='store_true', help='Verify and fix timestamps in markdown file')
    
    args = parser.parse_args()
    
    try:
        # Verify timestamps if requested
        if args.verify_timestamps and os.path.exists(args.input_file):
            verify_and_fix_timestamps(args.input_file, args.output_file)
        # If rearranging summary is requested
        elif args.rearrange and args.summary_file and os.path.exists(args.summary_file):
            # First verify and fix timestamps if needed
            if os.path.exists(args.summary_file):
                corrected_file = verify_and_fix_timestamps(args.summary_file)
                # Use the corrected file for rearrangement
                rearrange_summary_by_timestamp(corrected_file, args.chronological_output)
            else:
                rearrange_summary_by_timestamp(args.summary_file, args.chronological_output)
        # If summary file is provided
        elif args.summary_file and os.path.exists(args.summary_file):
            # First verify and fix timestamps if needed
            if os.path.exists(args.summary_file):
                corrected_file = verify_and_fix_timestamps(args.summary_file)
                # Use the corrected file for refinement
                refine_from_summaries(args.input_file, corrected_file, args.output_file)
            else:
                # Refine using the summary file
                refine_from_summaries(args.input_file, args.summary_file, args.output_file)
        else:
            # Download NLTK resources if needed - only for refinement operations
            download_nltk_resources()
            
            # Basic refinement
            refine_start_times(args.input_file, args.output_file)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)