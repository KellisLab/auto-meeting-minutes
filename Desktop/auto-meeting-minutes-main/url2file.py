#!/usr/bin/env python3
"""
url2file.py - Download Panopto video transcript from a URL

Usage: python url2file.py [url] [output_file]
If URL is not provided, the script will prompt for it.
If output file is not provided, it will use the video ID with .srt extension.

Example:
$ python url2file.py https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id=ef5959d0-da5f-4ac0-a1ad-b2aa001320a0&start=7960 my_transcript.srt

This will download the transcript and save it as my_transcript.srt
"""

import sys
import re
import os
import argparse
import requests


def extract_id_from_url(url):
    """
    Extract Panopto video ID from a URL
    
    Args:
        url (str): Panopto video URL
        
    Returns:
        str: Extracted video ID or None if no ID found
    """
    # Pattern to match Panopto video ID in the URL
    pattern = r'id=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
    
    # Search for the pattern in the URL
    match = re.search(pattern, url)
    
    # Return the ID if found, otherwise None
    if match:
        return match.group(1)
    else:
        return None


def download_transcript(video_id, output_file, language="English_USA"):
    """
    Download transcript for a Panopto video
    
    Args:
        video_id (str): Panopto video ID
        output_file (str): Path to save the downloaded transcript
        language (str, optional): Language code for the transcript. Default is "English_USA"
        
    Returns:
        bool: True if download successful, False otherwise
    """
    # Construct the transcript URL
    transcript_url = f"https://mit.hosted.panopto.com/Panopto/Pages/Transcription/GenerateSRT.ashx?id={video_id}&language={language}"
    
    try:
        # Send GET request to download the transcript
        response = requests.get(transcript_url)
        
        # Check if request was successful
        if response.status_code == 200:
            # Save the content to the output file
            with open(output_file, 'wb') as f:
                f.write(response.content)
            return True
        else:
            print(f"Error: Failed to download transcript. Status code: {response.status_code}", file=sys.stderr)
            return False
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return False


def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Download Panopto video transcript from a URL')
    parser.add_argument('url', nargs='?', help='Panopto video URL')
    parser.add_argument('output_file', nargs='?', help='Output file path (optional)')
    parser.add_argument('--language', default='English_USA', help='Language code for transcript (default: English_USA)')
    
    args = parser.parse_args()
    
    # Get URL from command line or prompt user
    url = args.url
    if not url:
        url = input("Enter Panopto video URL: ")
    
    # Extract video ID
    video_id = extract_id_from_url(url)
    
    if not video_id:
        print("Error: No valid Panopto video ID found in the URL", file=sys.stderr)
        sys.exit(1)
    
    # Determine output file path
    output_file = args.output_file
    if not output_file:
        output_file = f"{video_id}.srt"
    
    # Download the transcript
    if download_transcript(video_id, output_file, args.language):
        print(f"Transcript successfully downloaded to {output_file}")
    else:
        print("Failed to download transcript", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()