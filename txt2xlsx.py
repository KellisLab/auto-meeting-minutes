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

def txt_to_xlsx(input_file, output_file):
    """
    Convert meeting transcript to Excel format.
    
    The function expects a transcript in the format:
    00:00:00 Speaker Name: Text
    """
    # Regular expression to match timestamp, speaker, and text
    pattern = r'(\d{2}:\d{2}:\d{2}) ([^:]+): (.+)'
    
    # Read the transcript file
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract data using regex
    matches = re.findall(pattern, content)
    
    # Prepare data for DataFrame
    data = []
    
    # Track first occurrence of each speaker
    first_occurrences = {}
    
    # Collect all unique speakers first
    all_speakers = set()
    for time_str, speaker, text in matches:
        all_speakers.add(speaker)
    
    # Generate unique colors for all speakers
    speaker_colors = get_speaker_colors(all_speakers)
    
    for time_str, speaker, text in matches:
        seconds = time_to_seconds(time_str)
        
        # Check if this is the first occurrence of the speaker
        first_time = None
        first_seconds = None
        first_speaker = None
        
        if speaker not in first_occurrences:
            first_occurrences[speaker] = (time_str, seconds)
            first_time = time_str
            first_seconds = seconds
            first_speaker = speaker
        
        data.append({
            'Seconds': seconds,
            'Time': time_str,
            'First': first_speaker,
            'First_Time': first_time,
            'First_Seconds': first_seconds,
            'Name': speaker,
            'Text': text
        })
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    # Detect speaker topics
    speaker_topics = detect_speaker_topics(data)
    
    # Add topic metadata to DataFrame
    df['Topic_Number'] = None
    df['Topic_Start_Time'] = None
    df['Topic_Start_Seconds'] = None
    df['All_Occurrences'] = None
    
    # Populate topic metadata
    for speaker, topics in speaker_topics.items():
        # Convert topics to a JSON string for storage
        topic_json = json.dumps(topics)
        
        # For each topic
        for topic_num, topic in enumerate(topics, 1):
            # For each row index in this topic
            for row_idx in topic['indices']:
                # Update DataFrame with topic metadata
                df.loc[row_idx, 'Topic_Number'] = topic_num
                df.loc[row_idx, 'Topic_Start_Time'] = topic['start_time']
                df.loc[row_idx, 'Topic_Start_Seconds'] = topic['start_seconds']
    
    # Store all occurrences for each speaker
    for speaker in all_speakers:
        # Get all indices and timestamps for this speaker
        speaker_indices = df.index[df['Name'] == speaker].tolist()
        speaker_times = df.loc[df['Name'] == speaker, ['Seconds', 'Time']].to_dict('records')
        
        # Create a JSON string of all occurrences
        occurrences_json = json.dumps(speaker_times)
        
        # Update all rows for this speaker
        df.loc[df['Name'] == speaker, 'All_Occurrences'] = occurrences_json
    
    # Create Excel workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Meeting Transcript"
    
    # Add headers
    headers = [
        'Seconds', 'Time', 'First', 'First_Time', 'First_Seconds', 
        'Name', 'Text', 'Topic_Number', 'Topic_Start_Time', 
        'Topic_Start_Seconds', 'All_Occurrences'
    ]
    
    for col_num, header in enumerate(headers, 1):
        ws.cell(row=1, column=col_num).value = header
        ws.cell(row=1, column=col_num).font = Font(bold=True)
    
    # Calculate gradient positions based on time
    min_seconds = min(row['Seconds'] for row in data)
    max_seconds = max(row['Seconds'] for row in data)
    time_range = max_seconds - min_seconds
    
    # Add data and apply formatting
    for row_num, row_data in enumerate(data, 2):
        # Calculate time gradient position (0-1)
        if time_range > 0:
            time_position = (row_data['Seconds'] - min_seconds) / time_range
        else:
            time_position = 0
        
        # Get rainbow color for time
        time_color = get_rainbow_color(time_position)
        
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=row_num, column=col_num)
            
            # Get the value, handling new fields
            if header in row_data:
                cell.value = row_data[header]
            else:
                # Get the value from DataFrame for the added columns
                cell.value = df.iloc[row_num-2][header] if header in df.columns else None
            
            # Apply rainbow gradient to Seconds and First_Seconds columns
            if header in ('Seconds', 'First_Seconds', 'Topic_Start_Seconds'):
                if cell.value is not None:  # Only color cells with values
                    cell.fill = PatternFill(start_color=time_color, end_color=time_color, fill_type="solid")
            
            # Apply color to speaker names (except Manolis Kellis)
            elif header in ('Name', 'First') and cell.value and cell.value != "Manolis Kellis":
                speaker = cell.value
                if speaker in speaker_colors:
                    cell.fill = PatternFill(start_color=speaker_colors[speaker], 
                                           end_color=speaker_colors[speaker],
                                           fill_type="solid")
    
    # Auto-adjust column width
    for col_idx, header in enumerate(headers, 1):
        max_length = len(header) + 2  # Start with header length
        
        # Check data length
        for row_idx in range(2, len(data) + 2):
            cell_value = ws.cell(row=row_idx, column=col_idx).value
            if cell_value:
                # For JSON fields, limit the display length
                if header in ['All_Occurrences']:
                    max_length = max(max_length, 50)  # Cap JSON fields
                else:
                    max_length = max(max_length, min(len(str(cell_value)), 100))  # Cap at 100 chars
        
        # Adjust column width
        adjusted_width = max_length + 2
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = adjusted_width
    
    # Save the workbook
    wb.save(output_file)
    
    print(f"Transcript converted to Excel format: {output_file}")
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