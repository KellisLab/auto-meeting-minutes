#!/usr/bin/env python3
"""
fullpipeline.py - Complete transcript processing pipeline starting from a URL

This script integrates all components of the transcript processing pipeline:
1. url2id.py - Extract Panopto video ID from URL
2. url2meeting_name.py - Extract meeting name from URL for meaningful file names
3. url2file.py - Download transcript in SRT format
4. vtt2txt.py - Convert transcript to plain text with timestamps
5. txt2xlsx.py - Convert text to Excel format with formatting
6. refineStartTimes.py - Improve timestamp matching for speakers with multiple appearances
7. xlsx2html.py - Convert Excel to HTML with links and summaries
8. html_bold_converter.py - Convert markdown-style bold formatting to HTML bold tags

Usage:
    python fullpipeline.py [url] [--skip-refinement] [--html-format {simple|numbered}] [--language LANGUAGE] [--meeting-root DIRECTORY]
    [--skip-timestamps] [--skip-bold-conversion]

Example:
    python fullpipeline.py https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id=ef5959d0-da5f-4ac0-a1ad-b2aa001320a0 --meeting-root /data/meetings
"""

import os
import sys
import argparse
import importlib.util
import tempfile
import subprocess
import re
import shutil
import time
import datetime
import platform
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

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

def extract_date_from_name(name):
    """
    Extract date and time information from the meeting name.
    Expected format: YYYY.MM.DD_[Weekday][Time]
    Examples:
        - 2025.03.27_Thu5_20pm_Team_C_-_Compute
        - 2024.10.15_Tue3pm_Research_Meeting
    
    Returns a timestamp (seconds since epoch) if successful, None otherwise
    """
    try:
        # Pattern 1: YYYY.MM.DD_[Weekday][Hour]_[Minute][am/pm]
        # Example: 2025.03.27_Thu5_20pm
        pattern1 = r'(\d{4})\.(\d{2})\.(\d{2})_[A-Za-z]{3}(\d{1,2})_(\d{2})(am|pm)'
        
        # Pattern 2: YYYY.MM.DD_[Weekday][Hour][am/pm]
        # Example: 2024.10.15_Tue3pm
        pattern2 = r'(\d{4})\.(\d{2})\.(\d{2})_[A-Za-z]{3}(\d{1,2})(am|pm)'
        
        # Try the first pattern (with minutes)
        match = re.search(pattern1, name)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            hour = int(match.group(4))
            minute = int(match.group(5))
            ampm = match.group(6).lower()
            
            # Adjust hour for PM
            if ampm == 'pm' and hour < 12:
                hour += 12
            # Adjust for 12 AM
            if ampm == 'am' and hour == 12:
                hour = 0
            
            # Create a datetime object
            dt = datetime.datetime(year, month, day, hour, minute)
            return dt.timestamp()
        
        # Try the second pattern (without minutes)
        match = re.search(pattern2, name)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            hour = int(match.group(4))
            ampm = match.group(5).lower()
            
            # Adjust hour for PM
            if ampm == 'pm' and hour < 12:
                hour += 12
            # Adjust for 12 AM
            if ampm == 'am' and hour == 12:
                hour = 0
            
            # Create a datetime object
            dt = datetime.datetime(year, month, day, hour)
            return dt.timestamp()
        
        return None
    except Exception as e:
        print(f"Warning: Could not extract date from name: {e}")
        return None

def set_file_times_macos(path, timestamp):
    """
    Set all possible timestamps for a file on macOS, including:
    - Date Created (FSCreationDate)
    - Date Modified (FSContentChangeDate) 
    - Date Added (kMDItemDateAdded)
    - Date Last Opened (kMDItemLastUsedDate)
    """
    import os
    import datetime
    import subprocess
    
    try:
        # First use built-in os.utime to set modification and access times
        os.utime(path, (timestamp, timestamp))
        
        # Get absolute path
        abs_path = os.path.abspath(path)
        
        # Convert timestamp to datetime object
        dt = datetime.datetime.fromtimestamp(timestamp)
        
        # Try using xattr if available
        try:
            import xattr
            from osxmetadata import OSXMetaData
            
            # Create metadata object for the file
            md = OSXMetaData(abs_path)
            
            # Set last used date
            md.kMDItemLastUsedDate = dt
            
            # Set creation date
            md.kMDItemFSCreationDate = dt
            
            # Set content change date
            md.kMDItemFSContentChangeDate = dt
            
        except ImportError:
            print("Warning: xattr/osxmetadata libraries not installed, skipping extended attributes")
        
        # Additionally, try using touch command for creation time as fallback
        try:
            # Use touch command with -t flag to set creation time
            # Format timestamp as YYYYMMDDhhmm.ss
            time_str = dt.strftime('%Y%m%d%H%M.%S')
            subprocess.run(['touch', '-t', time_str, abs_path], check=True)
        except Exception as e:
            print(f"Warning: Could not use touch command: {e}")
        
        # Return success if basic timestamp was set
        return True
    except Exception as e:
        print(f"Warning: Could not set macOS timestamps for {path}: {e}")
        return False

def set_file_times_windows(path, timestamp):
    """
    Set all possible timestamps for a file on Windows, including:
    - Date Created (ctime)
    - Date Modified (mtime)
    - Date Accessed (atime)
    
    Uses Win32 API through a PowerShell script for setting creation time
    """
    try:
        # Convert timestamp to Windows PowerShell date format
        date_str = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        
        # Get absolute path
        abs_path = os.path.abspath(path).replace('\\', '\\\\')
        
        # Create a PowerShell script that uses .NET to set both creation and last write time
        # This is more reliable than using Get-Item/Set-ItemProperty
        ps_script = f"""
        $timestamp = [DateTime]::ParseExact('{date_str}', 'yyyy-MM-dd HH:mm:ss', $null)
        $file = New-Object System.IO.FileInfo -ArgumentList '{abs_path}'
        $file.CreationTime = $timestamp
        $file.LastWriteTime = $timestamp
        $file.LastAccessTime = $timestamp
        Write-Output "Timestamps updated for {abs_path}"
        """
        
        # Save script to a temporary file
        temp_script = tempfile.NamedTemporaryFile(suffix='.ps1', delete=False)
        temp_script_path = temp_script.name
        with open(temp_script_path, 'w') as f:
            f.write(ps_script)
        temp_script.close()
        
        # Execute the PowerShell script
        try:
            result = subprocess.run(['powershell', '-ExecutionPolicy', 'Bypass', '-File', temp_script_path], 
                                    check=True, capture_output=True, text=True)
            if result.returncode == 0:
                return True
            else:
                print(f"Warning: PowerShell script error: {result.stderr}")
                return False
        except subprocess.CalledProcessError as e:
            print(f"Warning: PowerShell error setting Windows timestamps: {e}")
            return False
        finally:
            # Clean up the temp script file
            try:
                os.unlink(temp_script_path)
            except:
                pass
    except Exception as e:
        print(f"Warning: Could not set Windows timestamps for {path}: {e}")
        return False

def set_file_times(path, timestamp):
    """
    Set the timestamps of a file or directory based on the current platform.
    """
    try:
        # Detect operating system
        system = platform.system()
        
        if system == 'Darwin':  # macOS
            return set_file_times_macos(path, timestamp)
        elif system == 'Windows':
            return set_file_times_windows(path, timestamp)
        else:  # Linux or other systems
            # Just use standard os.utime for other platforms
            os.utime(path, (timestamp, timestamp))
            return True
    except Exception as e:
        print(f"Warning: Could not set timestamp for {path}: {e}")
        return False

def set_timestamps_for_directory(directory, timestamp):
    """
    Set the timestamp for a directory and all files within it.
    """
    success_count = 0
    total_count = 0
    
    # Get operating system
    system = platform.system()
    
    print(f"Setting timestamps using {system}-specific methods...")
    
    # Walk through the directory
    for root, dirs, files in os.walk(directory):
        # Set timestamps for files
        for file in files:
            total_count += 1
            file_path = os.path.join(root, file)
            if set_file_times(file_path, timestamp):
                success_count += 1
        
        # Set timestamps for subdirectories
        for dir_name in dirs:
            total_count += 1
            dir_path = os.path.join(root, dir_name)
            if set_file_times(dir_path, timestamp):
                success_count += 1
    
    # Set timestamp for the directory itself
    total_count += 1
    if set_file_times(directory, timestamp):
        success_count += 1
    
    return success_count, total_count

def run_pipeline_from_url(url, skip_refinement=False, html_format="numbered", language="English_USA", 
                         meeting_root=None, skip_timestamps=False, skip_bold_conversion=False):
    """Run the complete transcript processing pipeline starting from a URL"""
    
    # Use meeting_root from environment variable if not specified
    if meeting_root is None:
        meeting_root = os.getenv('MEETING_ROOT_DIR', 'meetings')
    
    # Create meeting root directory if it doesn't exist
    if not os.path.exists(meeting_root):
        print(f"Creating meeting root directory: {meeting_root}")
        os.makedirs(meeting_root, exist_ok=True)
    
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Remember original directory
    original_dir = os.getcwd()
    
    # Step 1: Extract video ID from URL
    print("Step 1: Extracting video ID from URL...")
    url2id_path = os.path.join(script_dir, "url2id.py")
    
    try:
        url2id = import_module_from_file("url2id", url2id_path)
        video_id = url2id.extract_id_from_url(url)
        
        if not video_id:
            print("Error: Could not extract a valid video ID from the URL")
            sys.exit(1)
        
        print(f"Extracted video ID: {video_id}")
    except Exception as e:
        print(f"Error extracting video ID: {e}")
        sys.exit(1)
    
    # Step 1.5: Extract meeting name from URL
    print("Step 1.5: Extracting meeting name from URL...")
    url2meeting_name_path = os.path.join(script_dir, "url2meeting_name.py")
    
    try:
        url2meeting_name = import_module_from_file("url2meeting_name", url2meeting_name_path)
        meeting_name = url2meeting_name.get_meeting_name_from_viewer_page(url)
        
        if not meeting_name:
            print("Warning: Could not extract meeting name, using video ID as fallback")
            file_prefix = video_id
            meeting_folder_name = video_id
        else:
            # Sanitize meeting name for use in filenames
            file_prefix = sanitize_filename(meeting_name)
            meeting_folder_name = file_prefix
            print(f"Extracted meeting name: {meeting_name}")
            print(f"Using file prefix: {file_prefix}")
    except Exception as e:
        print(f"Warning: Error extracting meeting name: {e}")
        print("Using video ID as fallback for file naming")
        file_prefix = video_id
        meeting_folder_name = video_id
    
    # Create meeting-specific directory in the meeting root
    meeting_dir = os.path.join(meeting_root, meeting_folder_name)
    meeting_dir_abs = os.path.abspath(meeting_dir)
    if not os.path.exists(meeting_dir):
        print(f"Creating meeting directory: {meeting_dir}")
        os.makedirs(meeting_dir, exist_ok=True)
    
    # Step 2: Download transcript from Panopto
    print("Step 2: Downloading transcript...")
    url2file_path = os.path.join(script_dir, "url2file.py")
    
    try:
        url2file = import_module_from_file("url2file", url2file_path)
        srt_file = os.path.join(meeting_dir, f"{file_prefix}.srt")
        
        if url2file.download_transcript(video_id, srt_file, language):
            print(f"Transcript downloaded to: {srt_file}")
        else:
            print("Error: Failed to download transcript")
            sys.exit(1)
    except Exception as e:
        print(f"Error downloading transcript: {e}")
        sys.exit(1)
    
    # Step 3: Convert SRT to TXT (using VTT converter as they're similar formats)
    print("Step 3: Converting transcript to TXT...")
    vtt2txt_path = os.path.join(script_dir, "vtt2txt.py")
    txt_file = os.path.join(meeting_dir, f"{file_prefix}.txt")
    
    try:
        vtt2txt = import_module_from_file("vtt2txt", vtt2txt_path)
        txt_file = vtt2txt.vtt_to_txt(srt_file, txt_file)
        print(f"Transcript converted to TXT: {txt_file}")
    except Exception as e:
        print(f"Error converting to TXT: {e}")
        sys.exit(1)
    
    # Step 4: Convert TXT to XLSX
    print("Step 4: Converting TXT to XLSX...")
    txt2xlsx_path = os.path.join(script_dir, "txt2xlsx.py")
    xlsx_file = os.path.join(meeting_dir, f"{file_prefix}.xlsx")
    
    try:
        txt2xlsx = import_module_from_file("txt2xlsx", txt2xlsx_path)
        xlsx_file = txt2xlsx.txt_to_xlsx(txt_file, xlsx_file)
        print(f"TXT converted to XLSX: {xlsx_file}")
    except Exception as e:
        print(f"Error in TXT to XLSX conversion: {e}")
        sys.exit(1)
    
    # Step 5: Run refineStartTimes if not skipped
    refined_xlsx_file = xlsx_file
    if not skip_refinement:
        print("Step 5: Refining start times...")
        refinement_path = os.path.join(script_dir, "refineStartTimes.py")
        
        if os.path.exists(refinement_path):
            try:
                # Import and run the refinement module
                refine_start_times = import_module_from_file("refineStartTimes", refinement_path)
                
                # Create a refined version of the Excel file
                refined_xlsx_file = os.path.join(meeting_dir, f"{file_prefix}_refined.xlsx")
                refined_xlsx_file = refine_start_times.refine_start_times(xlsx_file, refined_xlsx_file)
                
                print(f"Start times refined and saved to: {refined_xlsx_file}")
            except Exception as e:
                print(f"Error in start time refinement: {e}")
                print("Continuing with pipeline using original Excel file...")
                refined_xlsx_file = xlsx_file
        else:
            print("Note: refineStartTimes.py not found. Skipping refinement step.")
    else:
        print("Step 5: Refining start times... (Skipped)")
    
    # Step 6: Convert XLSX to HTML with summaries
    print("Step 6: Generating HTML with summaries...")
    xlsx2html_path = os.path.join(script_dir, "xlsx2html.py")
    html_file = os.path.join(meeting_dir, f"{file_prefix}_speaker_summaries.html")
    summary_file = os.path.join(meeting_dir, f"{file_prefix}_meeting_summaries.html")
    speaker_summary_file = os.path.join(meeting_dir, f"{file_prefix}_speaker_summaries.md")
    meeting_summary_md_file = os.path.join(meeting_dir, f"{file_prefix}_meeting_summaries.md")
    
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
            print(f"Files saved to: {meeting_dir}")
            print(f"Speaker links HTML: {html_file}")
            print(f"Speaker summary Markdown: {speaker_summary_file}")
            print(f"Meeting summaries HTML: {summary_file}")
            print(f"Meeting summaries Markdown: {meeting_summary_md_file}")
        else:
            print("Warning: HTML conversion completed but output files may be missing.")
    except Exception as e:
        print(f"Error in XLSX to HTML conversion: {e}")
        sys.exit(1)
    
    # Step 7: Optionally refine the summaries with improved timestamp matching (if not done in Step 5)
    if not skip_refinement and os.path.exists(refinement_path) and os.path.exists(meeting_summary_md_file):
        print("Step 7: Post-processing summaries to improve timestamp accuracy...")
        try:
            # Import refineStartTimes module if not already imported
            if 'refine_start_times' not in locals():
                refine_start_times = import_module_from_file("refineStartTimes", refinement_path)
            
            # Create a version with refined timestamp mappings based on the summaries
            refined_post = os.path.join(meeting_dir, f"{file_prefix}_refined_post.xlsx")
            refined_post = refine_start_times.refine_from_summaries(
                refined_xlsx_file, meeting_summary_md_file, refined_post
            )
            
            print(f"Post-processed Excel file with improved timestamps: {refined_post}")
        except Exception as e:
            print(f"Warning: Error in summary post-processing: {e}")
            print("Original summaries are still available.")
    
    # Step 8: Set file and directory timestamps based on meeting date
    if not skip_timestamps:
        print("Step 8: Setting file and directory timestamps...")
        
        # Extract meeting date from folder name
        meeting_timestamp = extract_date_from_name(meeting_folder_name)
        
        if meeting_timestamp:
            # Convert timestamp to readable date for display
            date_str = datetime.datetime.fromtimestamp(meeting_timestamp).strftime('%Y-%m-%d %H:%M:%S')
            print(f"Extracted meeting date: {date_str}")
            
            # Set timestamps for all files and directories
            success_count, total_count = set_timestamps_for_directory(meeting_dir, meeting_timestamp)
            
            if success_count == total_count:
                print(f"Successfully set timestamps for all {total_count} files and directories")
            else:
                print(f"Set timestamps for {success_count} out of {total_count} files and directories")
        else:
            print("Warning: Could not extract date from meeting name, keeping original file timestamps")
    else:
        print("Step 8: Setting file and directory timestamps... (Skipped)")
    
    # Step 9: Convert markdown-style bold formatting to HTML bold tags
    if not skip_bold_conversion:
        print("Step 9: Converting markdown-style bold formatting to HTML bold tags...")
        html_bold_converter_path = os.path.join(script_dir, "html_bold_converter.py")
        
        try:
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
            
        except Exception as e:
            print(f"Warning: Error in bold formatting conversion: {e}")
            print("Original summaries are still available.")
    else:
        print("Step 9: Converting bold formatting... (Skipped)")
    
    return {
        "video_id": video_id,
        "meeting_name": meeting_name if meeting_name else video_id,
        "file_prefix": file_prefix,
        "meeting_dir": meeting_dir,
        "srt_file": os.path.join(meeting_dir, f"{file_prefix}.srt"),
        "txt_file": os.path.join(meeting_dir, f"{file_prefix}.txt"),
        "xlsx_file": os.path.join(meeting_dir, f"{file_prefix}.xlsx"),
        "refined_xlsx_file": os.path.join(meeting_dir, f"{file_prefix}_refined.xlsx") if not skip_refinement else None,
        "html_file": os.path.join(meeting_dir, f"{file_prefix}_speaker_summaries.html"),
        "summary_file": os.path.join(meeting_dir, f"{file_prefix}_meeting_summaries.html"),
        "speaker_summary_file": os.path.join(meeting_dir, f"{file_prefix}_speaker_summaries.md"),
        "meeting_summary_md_file": os.path.join(meeting_dir, f"{file_prefix}_meeting_summaries.md")
    }

def main():
    parser = argparse.ArgumentParser(
        description='Process video transcripts from URL through the complete pipeline'
    )
    parser.add_argument('url', nargs='?', help='Panopto video URL')
    parser.add_argument('--skip-refinement', action='store_true', 
                      help='Skip the start time refinement step')
    parser.add_argument('--html-format', choices=['simple', 'numbered'], default='numbered',
                      help='Output format for HTML: simple or numbered (default: numbered)')
    parser.add_argument('--language', default='English_USA',
                      help='Language code for transcript (default: English_USA)')
    parser.add_argument('--meeting-root', 
                      help='Root directory to store meeting files (default: from MEETING_ROOT_DIR env var or "meetings")')
    parser.add_argument('--use-modified-xlsx2html', action='store_true',
                      help='Use the modified xlsx2html.py script with improved timestamp matching')
    parser.add_argument('--skip-timestamps', action='store_true',
                      help='Skip setting file timestamps to match meeting date')
    parser.add_argument('--skip-bold-conversion', action='store_true',
                      help='Skip converting markdown-style bold formatting to HTML bold tags')
    
    args = parser.parse_args()
    
    # Get URL from command line or prompt user
    url = args.url
    if not url:
        url = input("Enter Panopto video URL: ")
    
    # If using modified xlsx2html, replace the module path
    if args.use_modified_xlsx2html:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        modified_path = os.path.join(script_dir, "xlsx2html_modified.py")
        if os.path.exists(modified_path):
            print("Using modified xlsx2html script with improved timestamp matching")
            # Monkey patch the import_module_from_file function to use the modified path
            original_import = import_module_from_file
            def patched_import(module_name, file_path):
                if module_name == "xlsx2html" and file_path.endswith("xlsx2html.py"):
                    return original_import("xlsx2html_modified", modified_path)
                return original_import(module_name, file_path)
            # Replace the function
            globals()["import_module_from_file"] = patched_import
        else:
            print("Warning: Modified xlsx2html script not found. Using original version.")
    
    run_pipeline_from_url(
        url,
        args.skip_refinement,
        args.html_format,
        args.language,
        args.meeting_root,
        args.skip_timestamps,
        args.skip_bold_conversion
    )

if __name__ == "__main__":
    main()