#!/usr/bin/env python3
"""
url2meeting_name.py - Extract Panopto meeting name from a URL without requiring authentication

Usage: python url2meeting_name.py [url] [--output file]
If URL is not provided, the script will prompt for it.
If output file is provided, the name will be written to the file.

Example:
$ python url2meeting_name.py https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id=ef5959d0-da5f-4ac0-a1ad-b2aa001320a0
Meeting Name: Introduction to Computer Science
"""

import sys
import re
import os
import argparse
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs

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

def get_meeting_name_from_viewer_page(url):
    """
    Extract meeting name from the Panopto viewer page HTML
    
    Args:
        url (str): Panopto video URL
        
    Returns:
        str: Meeting name or None if extraction fails
    """
    try:
        # Send GET request to the viewer page
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        
        # Check if request was successful
        if response.status_code == 200:
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Try to find title in various places
            
            # Method 1: Look for the title tag which typically includes the meeting name
            page_title = soup.title.string if soup.title else None
            if page_title and " - Panopto" in page_title:
                return page_title.split(" - Panopto")[0].strip()
            
            # Method 2: Try to find a header or heading element with the meeting name
            heading_elements = soup.find_all(['h1', 'h2', 'h3'], class_=re.compile(r'title|heading|header', re.I))
            for elem in heading_elements:
                if elem.text and len(elem.text.strip()) > 0:
                    return elem.text.strip()
            
            # Method 3: Look for metadata elements that might contain the title
            meta_title = soup.find('meta', property='og:title')
            if meta_title and meta_title.get('content'):
                title_content = meta_title.get('content')
                if " - Panopto" in title_content:
                    return title_content.split(" - Panopto")[0].strip()
                return title_content.strip()
            
            # Method 4: Look for specific div elements that might contain the title
            title_divs = soup.find_all('div', class_=re.compile(r'title|header|heading', re.I))
            for div in title_divs:
                if div.text and len(div.text.strip()) > 0:
                    return div.text.strip()
            
            # If all methods fail, return a default message
            return "Untitled Panopto Meeting"
        else:
            print(f"Error: Failed to fetch the viewer page. Status code: {response.status_code}", file=sys.stderr)
            return None
    
    except Exception as e:
        print(f"Error extracting meeting name: {e}", file=sys.stderr)
        return None

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Extract Panopto meeting name from a URL without requiring authentication')
    parser.add_argument('url', nargs='?', help='Panopto video URL')
    parser.add_argument('--output', '-o', help='Output file to write meeting name')
    
    args = parser.parse_args()
    
    # Get URL from command line or prompt user
    url = args.url
    if not url:
        url = input("Enter Panopto video URL: ")
    
    # Extract meeting name from the viewer page
    meeting_name = get_meeting_name_from_viewer_page(url)
    
    if not meeting_name:
        # Fallback: Try to extract a name from the URL itself
        video_id = extract_id_from_url(url)
        if video_id:
            meeting_name = f"Panopto Session {video_id[:8]}"
        else:
            print("Error: Could not extract meeting name from the URL", file=sys.stderr)
            sys.exit(1)
    
    # Output the meeting name
    if args.output:
        try:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(meeting_name)
            print(f"Meeting name written to: {args.output}")
        except Exception as e:
            print(f"Error writing to output file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"Meeting Name: {meeting_name}")
    
    return meeting_name

# Add installation instructions for required packages
def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import bs4
        return True
    except ImportError:
        print("Required package 'beautifulsoup4' is not installed.", file=sys.stderr)
        print("Install it using: pip install beautifulsoup4", file=sys.stderr)
        return False

if __name__ == "__main__":
    if check_dependencies():
        main()
    else:
        sys.exit(1)