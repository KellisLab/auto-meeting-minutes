#!/usr/bin/env python3
"""
transcript_pipeline.py - Process video transcripts through the complete pipeline

This script integrates the following components:
1. vtt2txt.py - Convert WebVTT subtitle files to plain text transcripts with timestamps
2. txt2xlsx.py - Convert the plain text transcript to Excel format with formatting
3. [refineStartTimes.py] - Currently a placeholder for future implementation
4. xlsx2html.py - Convert Excel transcript files to HTML with links and summaries

Usage:
    python transcript_pipeline.py input.vtt video_id [--skip-refinement] [--html-format {simple|numbered}]

Example:
    python transcript_pipeline.py lecture.vtt 757a2c7c-eb52-47d1-9b4a-b2a1014b530b --html-format=numbered
"""

import os
import sys
import argparse
import importlib.util
from pathlib import Path
import subprocess
import re

# Import our modules directly
def import_module_from_file(module_name, file_path):
    """Import a module from a file path"""
    if not os.path.exists(file_path):
        print(f"Error: Module file not found: {file_path}")
        sys.exit(1)
        
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def validate_video_id(video_id):
    """Validate that the provided string looks like a Panopto video ID"""
    # Basic validation for UUIDs/GUIDs which Panopto often uses
    # This pattern matches: 8-4-4-4-12 hexadecimal characters
    uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    if not re.match(uuid_pattern, video_id, re.IGNORECASE):
        print(f"Warning: The provided video ID '{video_id}' doesn't match the expected Panopto UUID format.")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(1)

def run_pipeline(vtt_file, video_id, skip_refinement=False, html_format="numbered"):
    """Run the complete transcript processing pipeline"""
    
    # Validate input file
    if not os.path.exists(vtt_file):
        print(f"Error: VTT file not found: {vtt_file}")
        sys.exit(1)
    
    # Validate video ID (basic check)
    validate_video_id(video_id)
    
    # Initialize file paths for intermediate outputs
    base_name = os.path.splitext(vtt_file)[0]
    txt_file = f"{base_name}.txt"
    xlsx_file = f"{base_name}.xlsx"
    html_file = f"{base_name}.speaker_summaries.html"
    summary_file = f"{base_name}_meeting_summaries.html"
    
    # Step 1: Import and run vtt2txt
    print("Step 1: Converting VTT to TXT...")
    
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    vtt2txt_path = os.path.join(script_dir, "vtt2txt.py")
    
    # Import the module
    try:
        vtt2txt = import_module_from_file("vtt2txt", vtt2txt_path)
        txt_file = vtt2txt.vtt_to_txt(vtt_file, txt_file)
        print(f"VTT converted to TXT: {txt_file}")
    except Exception as e:
        print(f"Error in VTT to TXT conversion: {e}")
        sys.exit(1)
    
    # Step 2: Import and run txt2xlsx
    print("Step 2: Converting TXT to XLSX...")
    txt2xlsx_path = os.path.join(script_dir, "txt2xlsx.py")
    
    try:
        # Import the module
        txt2xlsx = import_module_from_file("txt2xlsx", txt2xlsx_path)
        xlsx_file = txt2xlsx.txt_to_xlsx(txt_file, xlsx_file)
        print(f"TXT converted to XLSX: {xlsx_file}")
    except Exception as e:
        print(f"Error in TXT to XLSX conversion: {e}")
        sys.exit(1)
        
    # Step 3: Run refineStartTimes if not skipped (Currently a placeholder)
    if not skip_refinement:
        print("Step 3: Refining start times...")
        refinement_path = os.path.join(script_dir, "refineStartTimes.py")
        
        if os.path.exists(refinement_path):
            try:
                # This is a placeholder for when refineStartTimes.py is implemented
                print("Note: refineStartTimes.py is marked as TODO. Skipping refinement step.")
                # Would normally import and run the refinement module here
            except Exception as e:
                print(f"Error in start time refinement: {e}")
                # Continue with pipeline even if refinement fails
        else:
            print("Note: refineStartTimes.py not found. Skipping refinement step.")
    else:
        print("Step 3: Refining start times... (Skipped)")
    
    # Step 4: Import and run xlsx2html
    print("Step 4: Converting XLSX to HTML...")
    xlsx2html_path = os.path.join(script_dir, "xlsx2html.py")
    
    try:
        # Import the module
        xlsx2html = import_module_from_file("xlsx2html", xlsx2html_path)
        
        # Process the Excel file
        html_file, summary_file = xlsx2html.process_xlsx(
            xlsx_file,
            video_id,
            html_file,
            html_format
        )
        
        if html_file and summary_file:
            print("Pipeline completed successfully!")
            print(f"Speaker links HTML: {html_file}")
            print(f"Meeting summaries HTML: {summary_file}")
        else:
            print("Warning: HTML conversion completed but no output files were generated.")
    except Exception as e:
        print(f"Error in XLSX to HTML conversion: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description='Process video transcripts through the complete pipeline'
    )
    parser.add_argument('input_file', help='Input VTT file')
    parser.add_argument('video_id', help='Panopto video ID')
    parser.add_argument('--skip-refinement', action='store_true', 
                      help='Skip the start time refinement step')
    parser.add_argument('--html-format', choices=['simple', 'numbered'], default='numbered',
                      help='Output format for HTML: simple or numbered (default: numbered)')
    
    args = parser.parse_args()
    
    run_pipeline(
        args.input_file,
        args.video_id,
        args.skip_refinement,
        args.html_format
    )

if __name__ == "__main__":
    main()