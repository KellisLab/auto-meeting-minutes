#!/usr/bin/env python3
"""
pipeline.py - Process local VTT/SRT files to generate transcript summaries

This script processes local subtitle files without requiring a Panopto URL:
1. Takes a local VTT/SRT file as input
2. Converts subtitles to plain text with timestamps
3. Converts text to Excel format with formatting
4. Optionally refines timestamp matching for speakers with multiple appearances
5. Converts Excel to HTML with links and AI-generated summaries
6. Generates markdown summary files with proper formatting

Usage:
    python pipeline.py input_file [video_id] [--skip-refinement] [--html-format {simple|numbered}] 
                 [--output-dir DIRECTORY] [--meeting-name NAME]

Example:
    python pipeline.py lecture.srt ef5959d0-da5f-4ac0-a1ad-b2aa001320a0 --meeting-name "CS101 Lecture"
"""

import os
import sys
import argparse
import importlib.util
import tempfile
import re
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file if present
# This will load variables like MEETING_ROOT_DIR (default output directory) 
# and API_KEY (OpenAI API key for summaries)
load_dotenv()
print("Loading environment variables from .env file, if present...")
print(f"MEETING_ROOT_DIR from .env: {os.getenv('MEETING_ROOT_DIR', 'Not set')}")

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

def sanitize_filename(name):
    """Sanitize meeting name to create a valid filename"""
    # Replace invalid filename characters with underscores
    name = re.sub(r'[\\/*?:"<>|]', '_', name)
    # Replace multiple spaces with a single underscore
    name = re.sub(r'\s+', '_', name)
    # Limit filename length
    if len(name) > 100:
        name = name[:100]
    return name

def run_pipeline(input_file, video_id=None, skip_refinement=False, html_format="numbered", 
                output_dir=None, meeting_name=None):
    """Run the transcript processing pipeline starting from a local VTT/SRT file"""
    
    # Ensure input file exists
    if not os.path.exists(input_file):
        print(f"Error: Input file not found: {input_file}")
        sys.exit(1)
    
    # Create output directory if specified, use environment variable, or use default
    if output_dir is None:
        # First try to get the output directory from environment variable
        env_output_dir = os.getenv('MEETING_ROOT_DIR')
        if env_output_dir:
            output_dir = env_output_dir
            print(f"Using MEETING_ROOT_DIR from .env: {output_dir}")
        else:
            # Fallback to input file directory
            output_dir = os.path.dirname(input_file) or '.'
            print(f"Using default output directory: {os.path.abspath(output_dir)}")
    else:
        print(f"Using specified output directory: {output_dir}")
    
    # Ensure output_dir is an absolute path or make it absolute
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(output_dir)
    
    # Make sure to create the directory if it doesn't exist
    if not os.path.exists(output_dir):
        print(f"Creating output directory: {output_dir}")
        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception as e:
            print(f"Error creating output directory: {e}")
            sys.exit(1)
    
    # Determine file prefix for output files
    if meeting_name:
        file_prefix = sanitize_filename(meeting_name)
    else:
        # Use input filename as default prefix
        file_prefix = os.path.splitext(os.path.basename(input_file))[0]
    
    print(f"Using file prefix: {file_prefix}")
    
    # Prompt for video_id if not provided
    if video_id is None:
        print("\nA Panopto video ID is required to generate timestamp links.")
        print("Example: ef5959d0-da5f-4ac0-a1ad-b2aa001320a0")
        video_id = input("Enter Panopto video ID: ")
        
        # Validate video ID format
        if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', video_id):
            print("Warning: The provided video ID doesn't match the expected format.")
            if input("Continue anyway? (y/n): ").lower() != 'y':
                sys.exit(1)
    
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Remember original directory
    original_dir = os.getcwd()
    
    # Step 1: Convert VTT/SRT to TXT
    print("Step 1: Converting subtitle file to TXT...")
    vtt2txt_path = os.path.join(script_dir, "vtt2txt.py")
    txt_file = os.path.join(output_dir, f"{file_prefix}.txt")
    
    try:
        vtt2txt = import_module_from_file("vtt2txt", vtt2txt_path)
        txt_file = vtt2txt.vtt_to_txt(input_file, txt_file)
        print(f"Subtitle file converted to TXT: {txt_file}")
    except Exception as e:
        print(f"Error converting to TXT: {e}")
        sys.exit(1)
    
    # Step 2: Convert TXT to XLSX
    print("Step 2: Converting TXT to XLSX...")
    txt2xlsx_path = os.path.join(script_dir, "txt2xlsx.py")
    xlsx_file = os.path.join(output_dir, f"{file_prefix}.xlsx")
    
    try:
        txt2xlsx = import_module_from_file("txt2xlsx", txt2xlsx_path)
        xlsx_file = txt2xlsx.txt_to_xlsx(txt_file, xlsx_file)
        print(f"TXT converted to XLSX: {xlsx_file}")
    except Exception as e:
        print(f"Error in TXT to XLSX conversion: {e}")
        sys.exit(1)
    
    # Step 3: Run refineStartTimes if not skipped
    refined_xlsx_file = xlsx_file
    if not skip_refinement:
        print("Step 3: Refining start times...")
        refinement_path = os.path.join(script_dir, "refineStartTimes.py")
        
        if os.path.exists(refinement_path):
            try:
                # Import and run the refinement module
                refine_start_times = import_module_from_file("refineStartTimes", refinement_path)
                
                # Create a refined version of the Excel file
                refined_xlsx_file = os.path.join(output_dir, f"{file_prefix}_refined.xlsx")
                refined_xlsx_file = refine_start_times.refine_start_times(xlsx_file, refined_xlsx_file)
                
                print(f"Start times refined and saved to: {refined_xlsx_file}")
            except Exception as e:
                print(f"Error in start time refinement: {e}")
                print("Continuing with pipeline using original Excel file...")
                refined_xlsx_file = xlsx_file
        else:
            print("Note: refineStartTimes.py not found. Skipping refinement step.")
    else:
        print("Step 3: Refining start times... (Skipped)")
    
    # Step 4: Convert XLSX to HTML with summaries
    print("Step 4: Generating HTML with summaries...")
    xlsx2html_path = os.path.join(script_dir, "xlsx2html.py")
    html_file = os.path.join(output_dir, f"{file_prefix}_speaker_summaries.html")
    summary_file = os.path.join(output_dir, f"{file_prefix}_meeting_summaries.html")
    speaker_summary_file = os.path.join(output_dir, f"{file_prefix}_speaker_summaries.md")
    meeting_summary_md_file = os.path.join(output_dir, f"{file_prefix}_meeting_summaries.md")
    
    try:
        xlsx2html = import_module_from_file("xlsx2html", xlsx2html_path)
        
        # Process the refined Excel file
        result_files = xlsx2html.process_xlsx(
            refined_xlsx_file,
            video_id,
            html_file,
            html_format,
            summary_file,
            speaker_summary_file,
            meeting_summary_md_file
        )
        
        # Unpack result files, using the original names as fallback
        if result_files and len(result_files) == 4:
            html_file, summary_file, speaker_summary_file, meeting_summary_md_file = result_files
        
        if os.path.exists(html_file) and os.path.exists(summary_file):
            print("\nHTML generation completed successfully!")
            print(f"Files saved to: {output_dir}")
            print(f"Speaker links HTML: {html_file}")
            print(f"Speaker summary Markdown: {speaker_summary_file}")
            print(f"Meeting summaries HTML: {summary_file}")
            print(f"Meeting summaries Markdown: {meeting_summary_md_file}")
        else:
            print("Warning: HTML conversion completed but output files may be missing.")
    except Exception as e:
        print(f"Error in XLSX to HTML conversion: {e}")
        sys.exit(1)
    
    # Step 5: Optionally convert markdown-style bold formatting to HTML bold tags
    try:
        html_bold_converter_path = os.path.join(script_dir, "html_bold_converter.py")
        if os.path.exists(html_bold_converter_path):
            print("Step 5: Converting markdown-style bold formatting to HTML bold tags...")
            
            # Import and run the HTML bold converter module
            html_bold_converter = import_module_from_file("html_bold_converter", html_bold_converter_path)
            
            # Process the HTML summary files
            if os.path.exists(summary_file):
                html_bold_converter.process_html_file(summary_file)
                print(f"Converted bold formatting in meeting summaries HTML: {summary_file}")
            
            if os.path.exists(html_file):
                html_bold_converter.process_html_file(html_file)
                print(f"Converted bold formatting in speaker summaries HTML: {html_file}")
            
            # Process the markdown summary files
            if os.path.exists(meeting_summary_md_file):
                html_bold_converter.process_md_file(meeting_summary_md_file)
                print(f"Converted bold formatting in meeting summaries Markdown: {meeting_summary_md_file}")
            
            if os.path.exists(speaker_summary_file):
                html_bold_converter.process_md_file(speaker_summary_file)
                print(f"Converted bold formatting in speaker summaries Markdown: {speaker_summary_file}")
        else:
            print("Step 5: Converting bold formatting... (Skipped - converter script not found)")
    except Exception as e:
        print(f"Warning: Error in bold formatting conversion: {e}")
        print("Original summaries are still available.")
    
    return {
        "video_id": video_id,
        "file_prefix": file_prefix,
        "output_dir": output_dir,
        "input_file": input_file,
        "txt_file": txt_file,
        "xlsx_file": xlsx_file,
        "refined_xlsx_file": refined_xlsx_file if not skip_refinement else None,
        "html_file": html_file,
        "summary_file": summary_file,
        "speaker_summary_file": speaker_summary_file,
        "meeting_summary_md_file": meeting_summary_md_file
    }

def main():
    parser = argparse.ArgumentParser(
        description='Process local VTT/SRT files to generate transcript summaries'
    )
    parser.add_argument('input_file', help='Input VTT or SRT file')
    parser.add_argument('video_id', nargs='?', help='Panopto video ID for timestamp links')
    parser.add_argument('--skip-refinement', action='store_true', 
                      help='Skip the start time refinement step')
    parser.add_argument('--html-format', choices=['simple', 'numbered'], default='numbered',
                      help='Output format for HTML: simple or numbered (default: numbered)')
    parser.add_argument('--output-dir', 
                      help='Directory to store output files (default: MEETING_ROOT_DIR from .env or input file directory)')
    parser.add_argument('--meeting-name', 
                      help='Meeting name to use for output file prefixes (default: input filename)')
    
    args = parser.parse_args()
    
    # Run the pipeline with command line arguments
    # The function will handle .env and default directory logic
    run_pipeline(
        args.input_file,
        args.video_id,
        args.skip_refinement,
        args.html_format,
        args.output_dir,
        args.meeting_name
    )

if __name__ == "__main__":
    main()