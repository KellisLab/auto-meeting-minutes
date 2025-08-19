#!/usr/bin/env python3
"""
url2id.py - Extract Panopto video ID from a URL

Usage: python url2id.py [url]
If URL is not provided, the script will prompt for it.

Example:
$ python url2id.py https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id=ef5959d0-da5f-4ac0-a1ad-b2aa001320a0&start=7960
ef5959d0-da5f-4ac0-a1ad-b2aa001320a0
"""

import sys
import re
import argparse


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


def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Extract Panopto video ID from a URL')
    parser.add_argument('url', nargs='?', help='Panopto video URL')
    
    args = parser.parse_args()
    
    # Get URL from command line or prompt user
    url = args.url
    if not url:
        url = input("Enter Panopto video URL: ")
    
    # Extract video ID
    video_id = extract_id_from_url(url)
    
    # Print the result
    if video_id:
        print(video_id)
    else:
        print("Error: No valid Panopto video ID found in the URL", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()