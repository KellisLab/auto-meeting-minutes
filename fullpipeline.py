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
    python fullpipeline.py [url] [--skip-refinement] [--language LANGUAGE] [--meeting-root DIRECTORY]
    [--skip-timestamps] [--skip-bold-conversion] [--enhanced-summaries]

Example:
    python fullpipeline.py https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id=ef5959d0-da5f-4ac0-a1ad-b2aa001320a0 --meeting-root /data/meetings --enhanced-summaries
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

def fix_compound_words(text):
    """
    Fix compound words with hyphens that might have been expanded with spaces.
    
    Args:
        text (str): Text to fix
        
    Returns:
        str: Fixed text
    """
    return text
    # # Pattern to match "word - word" (a word, followed by space-hyphen-space, followed by another word)
    # pattern = r'\b([a-zA-Z]+)\s+-\s+([a-zA-Z]+)\b'
    
    # def replace_match(match):
    #     word1 = match.group(1).lower()
    #     word2 = match.group(2).lower()
        
    #     # Common prefixes and short words that are likely parts of compound words
    #     common_prefixes = {'self', 'post', 'pre', 'non', 'anti', 'co', 'counter', 'cross', 
    #                      'cyber', 'meta', 'multi', 'over', 'pseudo', 'quasi', 'semi', 
    #                      'sub', 'super', 'trans', 'ultra', 'under', 'vice', 'inter', 
    #                      'intra', 'micro', 'mid', 'mini', 'pro', 're', 'buy'}
        
    #     # Keep original capitalization while joining with hyphen
    #     if (len(word1) <= 4 or word1 in common_prefixes):
    #         return match.group(1) + '-' + match.group(2)
        
    #     # Not a compound word, keep as is
    #     return match.group(0)
    
    # # Apply the replacement
    # return re.sub(pattern, replace_match, text)

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
        pattern1 = r'(\d{4})\.(\d{2})\.(\d{2})_[A-Za-z]{3}(\d{1,2}).(\d{2})(am|pm)'
        
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

def run_pipeline_from_url(url, skip_refinement=False, language="English_USA", 
                         meeting_root=None, skip_timestamps=False, skip_bold_conversion=False,
                         use_enhanced_summaries=True):
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
    
    # Create meeting-specific directory in the meeting root with unique name to prevent overwriting
    meeting_folder_name = get_unique_directory_name(meeting_root, meeting_folder_name)
    meeting_dir = os.path.join(meeting_root, meeting_folder_name)
    meeting_dir_abs = os.path.abspath(meeting_dir)
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
        
        # Check if enhanced summaries are available
        # use_enhanced = use_enhanced_summaries and hasattr(xlsx2html, 'ENHANCED_SUMMARIES_AVAILABLE') and xlsx2html.ENHANCED_SUMMARIES_AVAILABLE
        use_enhanced = True
        if use_enhanced_summaries:
            print("Using enhanced speaker summaries with multiple topics...")
        
        # Process the refined Excel file
        result_files = xlsx2html.process_xlsx(
            refined_xlsx_file,
            video_id,
            html_file,
            speaker_summary_file,
            meeting_summary_md_file,
            use_enhanced_summaries=use_enhanced
        )
        
        # Unpack result files, using the original names as fallback
        if result_files and len(result_files) == 4:
            html_file, summary_file, speaker_summary_file, meeting_summary_md_file = result_files
        
        # Apply compound word fix to all summary files
        try:
            # Fix HTML files
            if os.path.exists(html_file):
                with open(html_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                html_content = fix_compound_words(html_content)
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)
            
            if os.path.exists(summary_file):
                with open(summary_file, 'r', encoding='utf-8') as f:
                    summary_content = f.read()
                summary_content = fix_compound_words(summary_content)
                with open(summary_file, 'w', encoding='utf-8') as f:
                    f.write(summary_content)
            
            # Fix markdown files
            if os.path.exists(speaker_summary_file):
                with open(speaker_summary_file, 'r', encoding='utf-8') as f:
                    md_content = f.read()
                md_content = fix_compound_words(md_content)
                with open(speaker_summary_file, 'w', encoding='utf-8') as f:
                    f.write(md_content)
            
            if os.path.exists(meeting_summary_md_file):
                with open(meeting_summary_md_file, 'r', encoding='utf-8') as f:
                    md_content = f.read()
                md_content = fix_compound_words(md_content)
                with open(meeting_summary_md_file, 'w', encoding='utf-8') as f:
                    f.write(md_content)
                    
            print("Applied compound word fixes to all summary files")
        except Exception as e:
            print(f"Warning: Error applying compound word fixes: {e}")
        
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
    
    # Step 7: Optionally convert markdown-style bold formatting to HTML bold tags
    if not skip_bold_conversion:
        try:
            html_bold_converter_path = os.path.join(script_dir, "html_bold_converter.py")
            if os.path.exists(html_bold_converter_path):
                print("Step 7: Converting markdown-style bold formatting to HTML bold tags...")
                
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
                print("Step 7: Converting bold formatting... (Skipped - converter script not found)")
        except Exception as e:
            print(f"Warning: Error in bold formatting conversion: {e}")
            print("Original summaries are still available.")
    else:
        print("Step 7: Converting bold formatting... (Skipped)")
    
    # Step 8: Set file and directory timestamps based on meeting date
    if not skip_timestamps:
        print("Step 8: Setting file and directory timestamps...")
        
        # Extract meeting date from folder name
        meeting_folder_name = re.sub(r'[\\/*?:"<>|]', '_', meeting_folder_name)
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
    parser.add_argument('--language', default='English_USA',
                      help='Language code for transcript (default: English_USA)')
    parser.add_argument('--meeting-root', 
                      help='Root directory to store meeting files (default: from MEETING_ROOT_DIR env var or "meetings")')
    parser.add_argument('--skip-timestamps', action='store_true',
                      help='Skip setting file timestamps to match meeting date')
    parser.add_argument('--skip-bold-conversion', action='store_true',
                      help='Skip converting markdown-style bold formatting to HTML bold tags')
    parser.add_argument('--enhanced-summaries', action='store_true',
                      help='Use enhanced speaker summaries with multiple topics (requires speaker_summary_utils.py)')
    
    args = parser.parse_args()
    
    # Get URL from command line or prompt user
    url = args.url
    if not url:
        url = input("Enter Panopto video URL: ")
    
    run_pipeline_from_url(
        url,
        args.skip_refinement,
        args.language,
        args.meeting_root,
        args.skip_timestamps,
        args.skip_bold_conversion,
        args.enhanced_summaries
    )

if __name__ == "__main__":
    main()