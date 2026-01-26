import re
import pandas as pd
import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
import random
import colorsys
import sys
import json

def time_to_seconds(time_str):
    """Convert HH:MM:SS to seconds."""
    h, m, s = map(int, time_str.split(':'))
    return h * 3600 + m * 60 + s

def generate_unique_colors(num_colors):
    """
    Generate a list of unique, visually distinct colors based on the HSV color model.
    This ensures colors won't repeat even with many speakers.
    Uses lighter colors for better readability.
    """
    colors = []
    
    # Use golden ratio for optimal distribution
    golden_ratio_conjugate = 0.618033988749895
    
    # Start at a random hue
    h = random.random()
    
    for i in range(num_colors):
        # Higher saturation and value for lighter, more readable colors
        s = 0.4  # Lower saturation for lighter colors
        v = 0.95  # High value for brightness
        
        # Convert HSV to RGB
        r, g, b = [int(x * 255) for x in colorsys.hsv_to_rgb(h, s, v)]
        color = f"{r:02x}{g:02x}{b:02x}"
        colors.append(color)
        
        # Increment hue by golden ratio for optimal spacing
        h += golden_ratio_conjugate
        h %= 1  # Keep within [0, 1]
    
    return colors

def get_speaker_colors(speakers):
    """Generate unique colors for each speaker (except Manolis Kellis)."""
    # Filter out "Manolis Kellis"
    filtered_speakers = [s for s in speakers if s != "Manolis Kellis"]
    
    # Generate unique colors
    colors = generate_unique_colors(len(filtered_speakers))
    
    # Map speakers to colors
    speaker_colors = {}
    for i, speaker in enumerate(filtered_speakers):
        speaker_colors[speaker] = colors[i]
    
    return speaker_colors

def get_rainbow_color(position):
    """Generate a color from rainbow gradient based on position (0-1)."""
    # Using HSV color space for rainbow effect (hue from 0 to 0.8)
    h = position * 0.8  # Full spectrum
    s = 0.7  # Saturation
    v = 0.9  # Value
    
    r, g, b = [int(x * 255) for x in colorsys.hsv_to_rgb(h, s, v)]
    return f"{r:02x}{g:02x}{b:02x}"

def detect_speaker_topics(data):
    """
    Detect potential topic changes for each speaker
    
    Args:
        data (list): List of transcript entries
        
    Returns:
        dict: Dictionary mapping speakers to their topics
    """
    # This simulates the functionality in speaker_summary_utils.enhance_speaker_tracking
    # but limited to just detecting topic changes and adding metadata
    
    # Sort entries by timestamp
    sorted_entries = sorted(data, key=lambda x: x['Seconds'])
    
    # Track speakers and their topics
    speaker_topics = {}
    current_topics = {}
    
    # First pass: detect topic boundaries
    for i, entry in enumerate(sorted_entries):
        speaker = entry['Name']
        seconds = entry['Seconds']
        
        # Initialize speaker if first time seen
        if speaker not in speaker_topics:
            speaker_topics[speaker] = []
            current_topics[speaker] = {
                'start_idx': i,
                'start_time': entry['Time'],
                'start_seconds': seconds,
                'text': [entry['Text']],
                'indices': [i]
            }
        else:
            # Check if this might be a new topic
            last_seconds = sorted_entries[current_topics[speaker]['indices'][-1]]['Seconds']
            time_gap = seconds - last_seconds
            
            if time_gap > 300:  # 5 minutes gap indicates new topic
                # Finalize current topic
                speaker_topics[speaker].append(current_topics[speaker])
                
                # Start new topic
                current_topics[speaker] = {
                    'start_idx': i,
                    'start_time': entry['Time'],
                    'start_seconds': seconds,
                    'text': [entry['Text']],
                    'indices': [i]
                }
            else:
                # Continue current topic
                current_topics[speaker]['text'].append(entry['Text'])
                current_topics[speaker]['indices'].append(i)
    
    # Add final topics
    for speaker, topic in current_topics.items():
        if topic['text']:  # Ensure not empty
            speaker_topics[speaker].append(topic)
    
    return speaker_topics

def parse_bracket_format(content):
    """
    Parse transcript in bracket format: [Speaker] HH:MM:SS followed by text
    
    Args:
        content (str): The transcript content
        
    Returns:
        list: List of (time_str, speaker, text) tuples
    """
    matches = []
    lines = content.strip().split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Look for speaker and timestamp pattern: [Speaker] HH:MM:SS
        speaker_time_match = re.match(r'\[([^\]]+)\]\s*(\d{1,2}:\d{2}:\d{2})', line)
        
        if speaker_time_match:
            speaker = speaker_time_match.group(1).strip()
            time_str = speaker_time_match.group(2)
            
            # Collect text from subsequent lines until next speaker/timestamp
            text_lines = []
            i += 1
            
            while i < len(lines):
                next_line = lines[i].strip()
                
                # Check if this is another speaker/timestamp line
                if re.match(r'\[([^\]]+)\]\s*(\d{1,2}:\d{2}:\d{2})', next_line):
                    break
                
                # Add non-empty lines to text
                if next_line:
                    text_lines.append(next_line)
                
                i += 1
            
            # Combine text lines
            if text_lines:
                text = ' '.join(text_lines)
                matches.append((time_str, speaker, text))
        else:
            i += 1
    
    return matches

def txt_to_xlsx(input_file, output_file):
    """
    Convert meeting transcript to Excel format.
    Input: HH:MM:SS SPEAKER: text
    """
    
    # Read and parse transcript
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse: HH:MM:SS SPEAKER: text
    pattern = r'(\d{2}:\d{2}:\d{2}) ([^:]+): (.+)'
    matches = re.findall(pattern, content)
    
    if not matches:
        raise ValueError("No valid transcript entries found")
    
    # Convert to DataFrame
    data = []
    for time_str, speaker, text in matches:
        # Convert HH:MM:SS to seconds
        h, m, s = map(int, time_str.split(':'))
        seconds = h * 3600 + m * 60 + s
        
        data.append({
            'Seconds': seconds,
            'Time': time_str,
            'Name': speaker,
            'Text': text
        })
    
    df = pd.DataFrame(data)
    
    # Save to Excel
    df.to_excel(output_file, index=False, engine='openpyxl')
    
    print(f"Converted {len(matches)} entries to {output_file}")
    return output_file

def get_column_letter(col_idx):
    """Convert column index to letter (1=A, 2=B, etc.)."""
    letter = ''
    while col_idx > 0:
        col_idx, remainder = divmod(col_idx - 1, 26)
        letter = chr(65 + remainder) + letter
    return letter

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python txt2xlsx.py input.txt [output.xlsx]")
        print("If output filename is not provided, it will use the input filename with .xlsx extension")
        sys.exit(1)
    
    input_file = sys.argv[1]
    
    # If output file is not specified, create one with the same name but .xlsx extension
    if len(sys.argv) < 3:
        output_file = input_file.rsplit('.', 1)[0] + '.xlsx'
    else:
        output_file = sys.argv[2]
    
    txt_to_xlsx(input_file, output_file)