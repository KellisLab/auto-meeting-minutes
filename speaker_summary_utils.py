"""
speaker_summary_utils.py - Utilities for enhanced speaker summary generation
Contains functions for tracking multiple speaker occurrences and generating improved summaries.
"""

import json
import re
import openai
import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# Default model from environment or fallback
MODEL = os.getenv("GPT_MODEL", "gpt-4o")

def compute_text_similarity(text1, text2):
    """
    Compute cosine similarity between two text strings
    
    Args:
        text1 (str): First text string
        text2 (str): Second text string
        
    Returns:
        float: Similarity score between 0 and 1
    """
    if not text1 or not text2:
        return 0.0

    # Create a TF-IDF vectorizer
    vectorizer = TfidfVectorizer()

    try:
        # Transform texts to vectors
        tfidf_matrix = vectorizer.fit_transform([text1, text2])

        # Compute cosine similarity
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        return similarity
    except:
        # Fallback if vectorization fails
        return 0.0

def enhance_speaker_tracking(transcript_data):
    """
    Enhance speaker tracking to include all occurrences and topic segmentation
    
    Args:
        transcript_data (list): List of transcript data dictionaries
        
    Returns:
        dict: Enhanced speaker data with all occurrences and topics
    """
    speaker_occurrences = {}
    current_topics = {}
    topic_changes = []

    # Sort by timestamp
    sorted_data = sorted(transcript_data, key=lambda x: x['seconds'])

    # First pass: detect potential topic changes
    for i, entry in enumerate(sorted_data):
        speaker = entry['name']

        # Initialize if first time seeing this speaker
        if speaker not in speaker_occurrences:
            speaker_occurrences[speaker] = []
            current_topics[speaker] = {
                'text': entry['text'],
                'start': entry['seconds'],
                'time_str': entry['time_str']
            }

        # Check if this might be a topic change for this speaker
        if speaker in current_topics:
            # If significant gap since last speaking turn (>5 minutes)
            time_gap = entry['seconds'] - current_topics[speaker]['start']
            if time_gap > 300:  # 5 minutes in seconds
                # Mark as potential topic change
                topic_changes.append({
                    'speaker': speaker,
                    'prev_end': current_topics[speaker]['start'],
                    'new_start': entry['seconds'],
                    'prev_text': current_topics[speaker]['text'],
                    'new_text': entry['text']
                })

                # Update current topic
                current_topics[speaker] = {
                    'text': entry['text'],
                    'start': entry['seconds'],
                    'time_str': entry['time_str']
                }

        # Add this occurrence
        speaker_occurrences[speaker].append({
            'seconds': entry['seconds'],
            'time_str': entry['time_str'],
            'text': entry['text'],
            'row_index': i if 'row_index' in entry else None
        })

    # Second pass: apply NLP to confirm topic changes
    confirmed_topics = {}
    for speaker, occurrences in speaker_occurrences.items():
        if not occurrences:
            continue

        confirmed_topics[speaker] = []
        current_topic = {
            'start_seconds': occurrences[0]['seconds'],
            'start_time': occurrences[0]['time_str'],
            'texts': [occurrences[0]['text']],
            'occurrences': [occurrences[0]]
        }

        for i in range(1, len(occurrences)):
            curr_occurrence = occurrences[i]
            # Check if this is a confirmed topic change
            is_topic_change = False

            for change in topic_changes:
                if (change['speaker'] == speaker and 
                    change['new_start'] == curr_occurrence['seconds']):
                    # Use similarity to confirm if this is truly a new topic
                    prev_text = ' '.join(current_topic['texts'])
                    new_text = curr_occurrence['text']

                    # If texts are dissimilar or significant time gap, confirm topic change
                    if (compute_text_similarity(prev_text, new_text) < 0.3 or
                        curr_occurrence['seconds'] - current_topic['occurrences'][-1]['seconds'] > 300):
                        is_topic_change = True
                        break

            if is_topic_change:
                # Finalize current topic
                confirmed_topics[speaker].append(current_topic)
                # Start new topic
                current_topic = {
                    'start_seconds': curr_occurrence['seconds'],
                    'start_time': curr_occurrence['time_str'],
                    'texts': [curr_occurrence['text']],
                    'occurrences': [curr_occurrence]
                }
            else:
                # Continue current topic
                current_topic['texts'].append(curr_occurrence['text'])
                current_topic['occurrences'].append(curr_occurrence)

        # Add the last topic
        if current_topic['texts']:
            confirmed_topics[speaker].append(current_topic)

    return confirmed_topics

def summarize_speaker_topic(speaker, topic_text, topic_number, api_key=None):
    """
    Summarize a specific topic discussion from a speaker
    
    Args:
        speaker (str): Speaker name
        topic_text (str): The text of their discussion on this topic
        topic_number (int): The topic number for this speaker
        api_key (str, optional): OpenAI API key
        
    Returns:
        dict: Dictionary with title and content of summary
    """
    if not api_key:
        from utils import get_api_key
        api_key = get_api_key()

    if not api_key:
        # Fallback if no API key
        return {
            'title': f"Topic {topic_number}",
            'content': f"Speaker discussed: {topic_text[:100]}..."
        }

    try:

        # Construct prompt for topic-specific summary
        prompt = (
            f"Generate a concise summary of this speaker's contribution to a specific topic.\n\n"
            f"Instructions:\n"
            f"1. Return a JSON object with two fields: 'title' and 'content'\n"
            f"2. The 'title' should be a brief (3-7 words) descriptive title of the topic discussed\n"
            f"3. The 'content' should be a detailed summary of the speaker's contribution\n"
            f"4. Use <b>bold</b> for important technical terms and concepts\n"
            f"5. Keep content to a single paragraph with no line breaks\n"
            f"6. Don't include the speaker's name in the content since it will be shown separately\n"
            f"7. Be technical and precise\n\n"
            f"TRANSCRIPT FROM {speaker} (TOPIC #{topic_number}):\n\n{topic_text}"
        )

        # Using chat completions API
        response = openai.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a technical meeting summarizer."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=800,
        )

        # Parse JSON response
        summary_json = json.loads(response.choices[0].message.content)
        return {
            'title': summary_json['title'],
            'content': summary_json['content']
        }

    except Exception as e:
        print(f"Error generating topic summary: {str(e)}")
        return {
            'title': f"Topic {topic_number}",
            'content': f"Speaker discussed: {topic_text[:100]}..."
        }

def generate_enhanced_speaker_summary_html(transcript_data, video_id, html_file=None, api_key=None, summaries_data=None):
    """
    Generate enhanced HTML with numbered speakers and topics with parenthesized numbers (1), (2)
    
    Args:
        transcript_data (list): List of transcript entry dictionaries
        video_id (str): Panopto video ID
        html_file (str, optional): Path to output HTML file
        api_key (str, optional): OpenAI API key
        summaries_data (dict, optional): Pre-generated summaries data
        
    Returns:
        str: Generated HTML content
    """
    # Add HTML header with styles
    html_content = '<!DOCTYPE html>\n<html>\n<head>\n<title>Speaker Summaries</title>\n'
    html_content += '<style>\n'
    # Basic styling
    html_content += 'body { font-family: Arial, sans-serif; margin: 20px; font-size: 11px; }\n'
    # Title styling - Cambria, 11px, #c0504d, underlined
    html_content += 'h1 { font-family: Cambria, serif; font-size: 11px; color: #c0504d; text-decoration: underline; margin-bottom: 15px; }\n'
    html_content += 'h1 a { color: #c0504d; text-decoration: underline; }\n'
    # Speaker styling - bold, purple, underlined
    html_content += '.speaker { font-weight: bold; color: #7030a0; text-decoration: underline; margin-bottom: 3px; }\n'
    # Topic styling
    html_content += '.topic { margin-left: 0px; margin-bottom: 3px; }\n'
    # Topic title styling - blue, underlined
    html_content += '.topic-title { font-weight: bold; color: #1f497d; text-decoration: underline; }\n'
    # Ordered list styling
    html_content += 'ol { list-style-position: outside; padding-left: 12px; margin-top: 5px; }\n'
    html_content += 'ol li { margin-bottom: 10px; }\n'
    # Link styling
    html_content += 'a { color: inherit; text-decoration: none; }\n'
    html_content += '.timestamp { color: #1155cc; }\n'
    html_content += '</style>\n</head>\n<body>\n'

    # Try to extract a title from the file path
    try:
        title = re.sub(r'(?<=\d)\.(\d{2})(am|pm)', r':\1\2', html_file)
        folder_name = os.path.basename(os.path.dirname(title))
        formatted_name = folder_name.replace('_', ' ')
        video_link = f'https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id={video_id}'
        html_content += f'<h1><a href="{video_link}">{formatted_name} <span style="color: #1155cc;">(link)</span></a></h1>\n'
    except:
        html_content += '<h1>Speaker Summaries</h1>\n'

    # Get summaries data if not provided
    if summaries_data is None:
        if not api_key:
            from utils import get_api_key
            api_key = get_api_key()
        summaries_data = generate_speaker_summaries_data(transcript_data, api_key)

    # Create an ordered list for speakers
    html_content += '<ol>\n'

    # Process each speaker
    for speaker_idx, (speaker, topics) in enumerate(summaries_data.items(), 1):
        # Speaker name as a list item with proper styling
        html_content += f'<li><div class="speaker">{speaker}</div>\n'

        # Process each topic for this speaker
        for i, topic in enumerate(topics, 1):
            # Get the pre-generated summary
            topic_summary = topic['summary']

            # Format timestamp link with hyperlink
            timestamp_seconds = topic['start_seconds']
            timestamp_str = topic['start_time']
            video_link = f'https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id={video_id}&start={timestamp_seconds}'

            # Add the topic with number in parentheses (1), (2), etc.
            html_content += f'<div class="topic">(<span class="topic-title">{i}) {topic_summary["title"]}</span> <a href="{video_link}"><span class="timestamp">({timestamp_str})</span></a>: {topic_summary["content"]}</div>\n'

            # # Add a line break between topics if not the last topic
            # if i < len(topics):
            #     html_content += '<br>\n'

        # Close the list item for this speaker
        html_content += '</li>\n'

    # Close the ordered list and HTML
    html_content += '</ol>\n</body>\n</html>'

    # Write to file if specified
    if html_file:
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"Generated enhanced speaker summary HTML with numbered speakers: {html_file}")

    return html_content

def generate_enhanced_speaker_summary_markdown(transcript_data, video_id, md_file=None, api_key=None, summaries_data=None):
    """
    Generate enhanced Markdown with speaker summaries and multiple topics per speaker
    
    Args:
        transcript_data (list): List of transcript entry dictionaries
        video_id (str): Panopto video ID
        md_file (str, optional): Path to output markdown file
        api_key (str, optional): OpenAI API key
        summaries_data (dict, optional): Pre-generated summaries data
        
    Returns:
        str: Generated markdown content
    """
    md_lines = []

    # Get summaries data if not provided
    if summaries_data is None:
        summaries_data = generate_speaker_summaries_data(transcript_data, api_key)

    try:
        title = re.sub(r'(?<=\d)\.(\d{2})(am|pm)', r':\1\2', md_file)
        folder_name = os.path.basename(os.path.dirname(title))
        formatted_name = folder_name.replace("_", " ")
        video_link = (
            f"https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id={video_id}"
        )
        md_lines.append(f"# [{formatted_name}]({video_link})\n")
    except:
        md_lines.append("# Meeting Summary\n")
    # Process each speaker
    for speaker, topics in summaries_data.items():
        # Speaker name as header
        md_lines.append(f"**{speaker}**")

        # Process each topic for this speaker
        for i, topic in enumerate(topics, 1):
            # Get the pre-generated summary
            topic_summary = topic['summary']

            # Format timestamp link with hyperlink
            timestamp_seconds = topic['start_seconds']
            timestamp_str = topic['start_time']
            video_link = f'https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id={video_id}&start={timestamp_seconds}'

            # Add the topic with number, timestamp and summary
            # Format exactly matches the example: **(1) Topic **[(timestamp)](link): Content
            md_lines.append(f"**({i}) {topic_summary['title']} **[({timestamp_str})]({video_link}): {topic_summary['content']}")

        # Add blank line between speakers if not the last speaker
        if speaker != list(summaries_data.keys())[-1]:
            md_lines.append("")

    # Write to file if specified
    if md_file:
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_lines))
        print(f"Generated enhanced speaker summary markdown: {md_file}")

    return '\n'.join(md_lines)

def generate_speaker_summaries_data(transcript_data, api_key=None):
    """
    Generate speaker topic summaries data structure to be used for both HTML and Markdown
    
    Args:
        transcript_data (list): List of transcript entry dictionaries
        api_key (str, optional): OpenAI API key
        
    Returns:
        dict: Enhanced speaker data with summaries
    """
    if not api_key:
        from utils import get_api_key
        api_key = get_api_key()

    # Get enhanced speaker topics
    topic_data = enhance_speaker_tracking(transcript_data)

    # Generate summaries for each topic - this is the key API call we want to make only once
    for speaker, topics in topic_data.items():
        for i, topic in enumerate(topics, 1):
            # Generate a summary for this specific topic
            topic_text = ' '.join(topic['texts'])

            # Store the summary in the topic data structure
            topic['summary'] = summarize_speaker_topic(speaker, topic_text, i, api_key)

    return topic_data