#!/usr/bin/env python3
"""
vtt2txt.py - Convert WebVTT subtitle files to plain text transcripts with timestamps
Supports multiple VTT formats:
1. Original format: HH:MM:SS,mmm with speaker names in text
2. New format: MM:SS.mmm with [SPEAKER_XX]: tags

Usage: python vtt2txt.py input.vtt [output.txt]
If output filename is not specified, it will use the input filename with .txt extension

Example conversions:
Format 1 (Original):
2 00:00:10,823 --> 00:00:13,439 Manolis Kellis: I'd love to sort of start from
→ 00:00:10 Manolis Kellis: I'd love to sort of start from

Format 2 (New):
00:01.263 --> 00:03.568
[SPEAKER_00]: The stale smell of old beer lingers.
→ 00:00:01 SPEAKER 00: The stale smell of old beer lingers.
"""

import sys
import re
import os

def parse_timestamp(timestamp_str):
    """
    Parse various timestamp formats and return seconds and formatted HH:MM:SS string
    
    Handles:
    - HH:MM:SS,mmm or HH:MM:SS.mmm
    - MM:SS.mmm or MM:SS,mmm
    - SS.mmm or SS,mmm
    """
    # Replace comma with period for consistency
    timestamp_str = timestamp_str.replace(',', '.')
    
    # Try to parse different formats
    parts = timestamp_str.split(':')
    
    if len(parts) == 3:  # HH:MM:SS.mmm
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(float(parts[2]))
    elif len(parts) == 2:  # MM:SS.mmm
        hours = 0
        minutes = int(parts[0])
        seconds = int(float(parts[1]))
    elif len(parts) == 1:  # SS.mmm
        hours = 0
        minutes = 0
        seconds = int(float(parts[0]))
    else:
        # Default fallback
        hours = minutes = seconds = 0
    
    # Calculate total seconds
    total_seconds = hours * 3600 + minutes * 60 + seconds
    
    # Format as HH:MM:SS
    formatted_hours = total_seconds // 3600
    formatted_minutes = (total_seconds % 3600) // 60
    formatted_seconds = total_seconds % 60
    
    return total_seconds, f"{formatted_hours:02d}:{formatted_minutes:02d}:{formatted_seconds:02d}"

def parse_original_format(remaining_text, formatted_time):
    '''
        Returning with format : HH:MM:SS SPEAKER: text
    '''
    # Original format: timestamp and text on same line
    # Look for speaker pattern "Speaker Name: text"
    speaker_inline_pattern = r'^([^:]+):\s*(.+)'
    speaker_inline_match = re.match(speaker_inline_pattern, remaining_text)
    
    if speaker_inline_match:
        speaker = speaker_inline_match.group(1).strip()# Speaker name
        text = speaker_inline_match.group(2).strip()# Text content
    else:
        # No clear speaker pattern, use the whole text
        speaker = "Speaker"
        text = remaining_text.strip()
    
    return f"{formatted_time} {speaker}: {text}"

def parse_new_format(content_line, formatted_time):
    '''
        Returning with format : HH:MM:SS SPEAKER: text
    '''
    # New format: text on next line    
    # Check if line contains speaker in brackets
    speaker_bracket_pattern = r'\[([^\]]+)\]:\s*(.+)'
    speaker_match = re.match(speaker_bracket_pattern, content_line)
    
    if speaker_match:
        speaker = speaker_match.group(1).replace('_', ' ')# Speaker name
        text = speaker_match.group(2).strip()# Text content
        return f"{formatted_time} {speaker}: {text}"
    #endif
    # Try to find speaker in "Name: text" format
    speaker_colon_pattern = r'^([^:]+):\s*(.+)'
    speaker_colon_match = re.match(speaker_colon_pattern, content_line)
    
    if speaker_colon_match:
        speaker = speaker_colon_match.group(1).strip()
        text = speaker_colon_match.group(2).strip()
        return f"{formatted_time} {speaker}: {text}"
    #endif
    
    # No speaker pattern found
    speaker = "Speaker"
    text = content_line.strip()
    return f"{formatted_time} {speaker}: {text}"

def vtt_to_txt(vtt_file, txt_file=None):
    """
    Convert a WebVTT file to a plain text transcript with timestamps
    
    Args:
        vtt_file (str): Path to input VTT file
        txt_file (str, optional): Path to output TXT file. If None, derived from vtt_file
    
    Returns:
        str: Path to the created text file
    """
    if txt_file is None:
        txt_file = os.path.splitext(vtt_file)[0] + '.txt'
    
    with open(vtt_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    output_lines = []
    # Skip the WEBVTT header if present
    #start_index = 0
    if lines and "WEBVTT" in lines[0]:
        lines = lines[1:]
    
    indx = 0
    while indx < len(lines):
        line = lines[indx].strip()
        # 1. remove any leading blank lines
        # 2. Check if line is just a number (cue identifier in original format)
        if not line or re.match(r'^\d+$', line):
            indx += 1
            continue

        # 3. Check if this line contains a timestamp
        # Pattern for any timestamp format with -->
        timestamp_pattern = r'([0-9:,\.]+)\s*-->\s*([0-9:,\.]+)'
        timestamp_match = re.search(timestamp_pattern, line)
        
        if timestamp_match:
            # 3.1 Get the start timestamp
            start_timestamp = timestamp_match.group(1)
            
            # 3.2 Parse the timestamp
            _, formatted_time = parse_timestamp(start_timestamp)# formatted HH:MM:SS string
            
            # 3.3 Check if there's text on the same line (original format)
            remaining_text = line[timestamp_match.end():].strip()
            
            if remaining_text:
                output_lines.append(parse_original_format(remaining_text, formatted_time))
            else:
                # New format: text on next line
                indx += 1
                if indx < len(lines):
                    content_line = lines[indx].strip()
                    if content_line:
                        output_lines.append(parse_new_format(content_line, formatted_time))                    
                #endif
            #endif
        #endif
        # Move to next line
        indx += 1   
    #endwhile
    
    # Write the formatted transcript to the output file
    with open(txt_file, 'w', encoding='utf-8') as f:
        for line in output_lines:
            f.write(f"{line}\n")# output format : HH:MM:SS SPEAKER: text
    
    return txt_file

def main():
    # Check arguments
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} input.vtt [output.txt]")
        sys.exit(1)
    
    vtt_file = sys.argv[1]
    txt_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        output_file = vtt_to_txt(vtt_file, txt_file)
        print(f"Converted {vtt_file} to {output_file}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()