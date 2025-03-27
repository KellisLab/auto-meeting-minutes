#!/usr/bin/env python3
"""
vtt2txt.py - Convert WebVTT subtitle files to plain text transcripts with timestamps
Usage: python vtt2txt.py input.vtt [output.txt]
If output filename is not specified, it will use the input filename with .txt extension

Example conversion:
From VTT:
2 00:00:10,823 --> 00:00:13,439 Manolis Kellis: I'd love to sort of start from

To TXT:
00:00:10 Manolis Kellis: I'd love to sort of start from
"""

import sys
import re
import os

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
    start_index = 0
    if lines and "WEBVTT" in lines[0]:
        start_index = 1
    
    # Process the VTT content
    i = start_index
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines
        if not line:
            i += 1
            continue
            
        # Check if line is a cue number (just a number)
        if re.match(r'^\d+$', line):
            # Next line should be the timestamp
            i += 1
            if i < len(lines):
                timestamp_line = lines[i].strip()
                # Look for timestamps in format 00:00:00,000 --> 00:00:00,000
                timestamp_match = re.search(r'(\d{2}:\d{2}:\d{2})[,\.]\d{3}\s*-->', timestamp_line)
                
                if timestamp_match:
                    # Get the full time part (00:00:00)
                    full_time = timestamp_match.group(1)
                    
                    # Move to the next line which contains the text content
                    i += 1
                    if i < len(lines):
                        text_line = lines[i].strip()
                        if text_line:
                            # Format as "00:00:00 Speaker: Text"
                            output_lines.append(f"{full_time} {text_line}")
        
        # Move to next line
        i += 1
    
    # Write the formatted transcript to the output file
    with open(txt_file, 'w', encoding='utf-8') as f:
        for line in output_lines:
            f.write(f"{line}\n")
    
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