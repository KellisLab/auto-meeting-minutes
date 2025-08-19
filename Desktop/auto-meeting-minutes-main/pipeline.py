#!/usr/bin/env python3
"""
pipeline.py - Process local VTT/SRT files to generate transcript summaries

This script processes local subtitle files without requiring a Panopto URL:
1. Takes a local VTT/SRT file as input
2. Converts subtitles to plain text with timestamps
3. Converts text to Excel format with formatting
4. Optionally refines timestamp matching for speakers with multiple appearances
5. Converts Excel to HTML with links and AI-generated summaries (with or without video links)
6. Generates markdown summary files with proper formatting

Usage:
    python pipeline.py input_file [video_id] [--skip-refinement] [--html-format {simple|numbered}] 
                 [--output-dir DIRECTORY] [--meeting-name NAME] [--no-enhanced-summaries] [--skip-bold-conversion]

Example:
    # With video ID for clickable links
    python pipeline.py lecture.srt ef5959d0-da5f-4ac0-a1ad-b2aa001320a0 --meeting-name "CS101 Lecture"
    
    # Without video ID (no clickable links, just timestamps)
    python pipeline.py lecture.srt --meeting-name "CS101 Lecture" --no-video-links
"""

import os
import sys
import argparse
import importlib.util
import tempfile
import re
from pathlib import Path
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file if present
# This will load variables like MEETING_ROOT_DIR (default output directory) 
# and API_KEY (OpenAI API key for summaries)
load_dotenv()
logger.info("Loading environment variables from .env file, if present...")
logger.info(f"MEETING_ROOT_DIR from .env: {os.getenv('MEETING_ROOT_DIR', 'Not set')}")
logger.info(f"Using API model: {os.getenv('GPT_MODEL', 'Not set - will use default')}")

# Import our modules directly
def import_module_from_file(module_name, file_path):
    """Import a module from a file path"""
    if not os.path.exists(file_path):
        logger.error(f"Error: Module file not found: {file_path}")
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

def get_unique_directory_name(base_dir, folder_name):
    """
    Generate a unique directory name by appending a suffix if necessary.
    
    Args:
        base_dir (str): Base directory
        folder_name (str): Desired folder name
        
    Returns:
        str: Unique folder name
    """
    # Initial path
    dir_path = os.path.join(base_dir, folder_name)
    
    # Check if directory exists and has content
    if os.path.exists(dir_path) and os.listdir(dir_path):
        # Directory exists and has content, append suffix
        counter = 2
        while True:
            new_name = f"{folder_name} ({counter})"  # Added space before parenthesis
            new_path = os.path.join(base_dir, new_name)
            
            # Check if this new name is available or is empty
            if not os.path.exists(new_path) or not os.listdir(new_path):
                return new_name
            
            counter += 1
    
    # Directory doesn't exist or is empty
    return folder_name

def validate_video_id(video_id):
    """
    Validate video ID format (Panopto UUID format)
    
    Args:
        video_id (str): Video ID to validate
        
    Returns:
        bool: True if valid format, False otherwise
    """
    if not video_id:
        return False
    return bool(re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', video_id))

def run_pipeline(input_file, video_id=None, skip_refinement=False, html_format="numbered", 
                output_dir=None, meeting_name=None, enhanced_summaries=True, skip_bold_conversion=False,
                no_video_links=False):
    """Run the transcript processing pipeline starting from a local VTT/SRT file"""
    
    # Ensure input file exists
    if not os.path.exists(input_file):
        logger.error(f"Error: Input file not found: {input_file}")
        sys.exit(1)
    
    # Create output directory if specified, use environment variable, or use default
    if output_dir is None:
        # First try to get the output directory from environment variable
        env_output_dir = os.getenv('MEETING_ROOT_DIR')
        if env_output_dir:
            output_dir = env_output_dir
            logger.info(f"Using MEETING_ROOT_DIR from .env: {output_dir}")
        else:
            # Fallback to input file directory
            output_dir = os.path.dirname(input_file) or '.'
            logger.info(f"Using default output directory: {os.path.abspath(output_dir)}")
    else:
        logger.info(f"Using specified output directory: {output_dir}")
    
    # Ensure output_dir is an absolute path or make it absolute
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(output_dir)
    
    # Make sure to create the directory if it doesn't exist
    if not os.path.exists(output_dir):
        logger.info(f"Creating output directory: {output_dir}")
        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception as e:
            logger.error(f"Error creating output directory: {e}")
            sys.exit(1)
    
    # Determine file prefix for output files
    if meeting_name:
        file_prefix = sanitize_filename(meeting_name)
        meeting_folder_name = file_prefix
    else:
        # Use input filename as default prefix
        file_prefix = os.path.splitext(os.path.basename(input_file))[0]
        meeting_folder_name = file_prefix
    
    # Create meeting-specific directory within the output directory
    meeting_folder_name = get_unique_directory_name(output_dir, meeting_folder_name)
    meeting_dir = os.path.join(output_dir, meeting_folder_name)
    logger.info(f"Creating meeting directory: {meeting_dir}")
    os.makedirs(meeting_dir, exist_ok=True)
    
    logger.info(f"Using file prefix: {file_prefix}")
    
    # Handle video ID for timestamp links
    use_video_links = False
    if not no_video_links:
        if video_id is None:
            print("\nTo generate clickable timestamp links, a video ID is needed.")
            print("You can either:")
            print("1. Provide a Panopto video ID (format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)")
            print("2. Skip video links and generate summaries with text-only timestamps")
            print("")
            choice = input("Enter video ID or press Enter to skip video links: ").strip()
            
            if choice:
                video_id = choice
                if validate_video_id(video_id):
                    use_video_links = True
                    logger.info(f"Using video ID: {video_id}")
                else:
                    logger.warning("Warning: The provided video ID doesn't match the expected format.")
                    if input("Continue anyway? (y/n): ").lower() == 'y':
                        use_video_links = True
                    else:
                        logger.info("Proceeding without video links")
                        video_id = None
            else:
                logger.info("Proceeding without video links")
                video_id = None
        else:
            if validate_video_id(video_id):
                use_video_links = True
                logger.info(f"Using provided video ID: {video_id}")
            else:
                logger.warning("Warning: The provided video ID doesn't match the expected format.")
                use_video_links = True  # Still try to use it
    else:
        logger.info("Video links disabled by user request")
        video_id = None
    
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Remember original directory
    original_dir = os.getcwd()
    
    # Step 1: Convert VTT/SRT to TXT
    logger.info("Step 1: Converting subtitle file to TXT...")
    vtt2txt_path = os.path.join(script_dir, "vtt2txt.py")
    txt_file = os.path.join(meeting_dir, f"{file_prefix}.txt")
    
    try:
        vtt2txt = import_module_from_file("vtt2txt", vtt2txt_path)
        txt_file = vtt2txt.vtt_to_txt(input_file, txt_file)
        logger.info(f"Subtitle file converted to TXT: {txt_file}")
    except Exception as e:
        logger.error(f"Error converting to TXT: {e}")
        sys.exit(1)
    
    # Step 2: Convert TXT to XLSX
    logger.info("Step 2: Converting TXT to XLSX...")
    txt2xlsx_path = os.path.join(script_dir, "txt2xlsx.py")
    xlsx_file = os.path.join(meeting_dir, f"{file_prefix}.xlsx")
    
    try:
        txt2xlsx = import_module_from_file("txt2xlsx", txt2xlsx_path)
        xlsx_file = txt2xlsx.txt_to_xlsx(txt_file, xlsx_file)
        logger.info(f"TXT converted to XLSX: {xlsx_file}")
    except Exception as e:
        logger.error(f"Error in TXT to XLSX conversion: {e}")
        sys.exit(1)
    
    # Step 3: Run refineStartTimes if not skipped
    refined_xlsx_file = xlsx_file
    if not skip_refinement:
        logger.info("Step 3: Refining start times...")
        refinement_path = os.path.join(script_dir, "refineStartTimes.py")
        
        if os.path.exists(refinement_path):
            try:
                # Import and run the refinement module
                refine_start_times = import_module_from_file("refineStartTimes", refinement_path)
                
                # Create a refined version of the Excel file
                refined_xlsx_file = os.path.join(meeting_dir, f"{file_prefix}_refined.xlsx")
                refined_xlsx_file = refine_start_times.refine_start_times(xlsx_file, refined_xlsx_file)
                
                logger.info(f"Start times refined and saved to: {refined_xlsx_file}")
            except Exception as e:
                logger.error(f"Error in start time refinement: {e}")
                logger.warning("Continuing with pipeline using original Excel file...")
                refined_xlsx_file = xlsx_file
        else:
            logger.warning("Note: refineStartTimes.py not found. Skipping refinement step.")
    else:
        logger.info("Step 3: Refining start times... (Skipped)")
    
    # Step 4: Convert XLSX to HTML with summaries
    logger.info("Step 4: Generating HTML with summaries...")
    xlsx2html_path = os.path.join(script_dir, "xlsx2html.py")
    html_file = os.path.join(meeting_dir, f"{file_prefix}_speaker_summaries.html")
    summary_file = os.path.join(meeting_dir, f"{file_prefix}_meeting_summaries.html")
    speaker_summary_file = os.path.join(meeting_dir, f"{file_prefix}_speaker_summaries.md")
    meeting_summary_md_file = os.path.join(meeting_dir, f"{file_prefix}_meeting_summaries.md")
    
    try:
        xlsx2html = import_module_from_file("xlsx2html", xlsx2html_path)
        
        # Process the refined Excel file with corrected parameter order
        try:
            if use_video_links and video_id:
                logger.info("Creating HTML with speaker summaries and clickable timestamp links...")
            else:
                logger.info("Creating HTML with speaker summaries and text-only timestamps...")
            
            result_files = xlsx2html.process_xlsx(
                refined_xlsx_file,
                video_id,  # This can be None now
                html_file,
                speaker_summary_file,
                meeting_summary_md_file,
                use_enhanced_summaries=enhanced_summaries
            )
            
            # Unpack result files, using the original names as fallback
            if result_files and len(result_files) == 4:
                html_file, summary_file, speaker_summary_file, meeting_summary_md_file = result_files
                
            logger.info("\nHTML generation completed successfully!")
            logger.info(f"Files saved to: {meeting_dir}")
            logger.info(f"Speaker links HTML: {html_file}")
            logger.info(f"Speaker summary Markdown: {speaker_summary_file}")
            logger.info(f"Meeting summaries HTML: {summary_file}")
            logger.info(f"Meeting summaries Markdown: {meeting_summary_md_file}")
            
            if not use_video_links:
                logger.info("Note: Generated summaries contain text-only timestamps (no clickable links)")
                
        except Exception as e:
            logger.error(f"Error in xlsx2html processing: {e}")
            logger.warning(f"Warning: Error in HTML generation: {str(e)}")
            logger.info("Proceeding with available files...")
            
    except Exception as e:
        logger.error(f"Error in XLSX to HTML conversion: {e}")
        sys.exit(1)
    
    # Step 5: Convert markdown-style bold formatting to HTML bold tags (unless skipped)
    if not skip_bold_conversion:
        try:
            html_bold_converter_path = os.path.join(script_dir, "html_bold_converter.py")
            if os.path.exists(html_bold_converter_path):
                logger.info("Step 5: Converting markdown-style bold formatting to HTML bold tags...")
                
                # Import and run the HTML bold converter module
                html_bold_converter = import_module_from_file("html_bold_converter", html_bold_converter_path)
                
                # Process the HTML summary files
                if os.path.exists(summary_file):
                    html_bold_converter.process_html_file(summary_file)
                    logger.info(f"Converted bold formatting in meeting summaries HTML: {summary_file}")
                
                if os.path.exists(html_file):
                    html_bold_converter.process_html_file(html_file)
                    logger.info(f"Converted bold formatting in speaker summaries HTML: {html_file}")
                
                # Process the markdown summary files
                if os.path.exists(meeting_summary_md_file):
                    html_bold_converter.process_md_file(meeting_summary_md_file)
                    logger.info(f"Converted bold formatting in meeting summaries Markdown: {meeting_summary_md_file}")
                
                if os.path.exists(speaker_summary_file):
                    html_bold_converter.process_md_file(speaker_summary_file)
                    logger.info(f"Converted bold formatting in speaker summaries Markdown: {speaker_summary_file}")
            else:
                logger.info("Step 5: Converting bold formatting... (Skipped - converter script not found)")
        except Exception as e:
            logger.warning(f"Warning: Error in bold formatting conversion: {e}")
            logger.info("Original summaries are still available.")
    else:
        logger.info("Step 5: Converting bold formatting... (Skipped by user request)")
    
    return {
        "video_id": video_id,
        "file_prefix": file_prefix,
        "output_dir": output_dir,
        "meeting_dir": meeting_dir,
        "input_file": input_file,
        "txt_file": txt_file,
        "xlsx_file": xlsx_file,
        "refined_xlsx_file": refined_xlsx_file if not skip_refinement else None,
        "html_file": html_file,
        "summary_file": summary_file,
        "speaker_summary_file": speaker_summary_file,
        "meeting_summary_md_file": meeting_summary_md_file,
        "use_video_links": use_video_links
    }

def main():
    parser = argparse.ArgumentParser(
        description='Process local VTT/SRT files to generate transcript summaries'
    )
    parser.add_argument('input_file', help='Input VTT or SRT file')
    parser.add_argument('video_id', nargs='?', help='Panopto video ID for timestamp links (optional)')
    parser.add_argument('--skip-refinement', action='store_true', 
                      help='Skip the start time refinement step')
    parser.add_argument('--html-format', choices=['simple', 'numbered'], default='numbered',
                      help='Output format for HTML: simple or numbered (default: numbered)')
    parser.add_argument('--output-dir', 
                      help='Directory to store output files (default: MEETING_ROOT_DIR from .env or input file directory)')
    parser.add_argument('--meeting-name', 
                      help='Meeting name to use for output file prefixes (default: input filename)')
    parser.add_argument('--no-enhanced-summaries', action='store_true',
                      help='Disable enhanced speaker summaries with multiple topics (enabled by default)')
    parser.add_argument('--skip-bold-conversion', action='store_true',
                      help='Skip converting markdown-style bold formatting to HTML bold tags')
    parser.add_argument('--no-video-links', action='store_true',
                      help='Generate summaries without clickable video timestamp links (text-only timestamps)')
    
    args = parser.parse_args()
    
    # Run the pipeline with command line arguments
    # The function will handle .env and default directory logic
    run_pipeline(
        args.input_file,
        args.video_id,
        args.skip_refinement,
        args.html_format,
        args.output_dir,
        args.meeting_name,
        not args.no_enhanced_summaries,  # Inverted flag since enhanced summaries is now default
        args.skip_bold_conversion,
        args.no_video_links
    )

if __name__ == "__main__":
    main()