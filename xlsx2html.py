import sys
import os
import pandas as pd
import argparse
import re
import openai
from dotenv import load_dotenv

# Import utility functions from utils.py
from utils import (
    parse_json,
    seconds_to_time_str,
    verify_timestamp_format,
    extract_transcript_data,
    extract_unique_speakers,
    create_time_batches,
    extract_text_for_batch,
    update_speaker_timestamps_for_topics,
    extract_topics_from_summary,
    get_api_key,
)

from meetinglogger import logger
import pandas as pd  # Add pandas import

# -------------------------------------------------------------
# Constants and Configuration
# -------------------------------------------------------------
# load API KEY from .env
load_dotenv()
# Access the API key
OPENAI_API_KEY = os.getenv("API_KEY")
MODEL = os.getenv("GPT_MODEL", "gpt-4o")
# Default batch size for meeting summaries (in minutes) 
DEFAULT_BATCH_SIZE_MINUTES = 25
ENHANCED_SUMMARIES_AVAILABLE = True


# -------------------------------------------------------------
# HTML and Markdown Generation Functions
# -------------------------------------------------------------
def generate_meeting_summaries_html(
    batches, batch_summaries, video_id, html_file, transcript_data=None
):
    """
    Generate HTML file with meeting batch summaries that include clickable timestamp links
    for both batches and individual topics within each batch.
    Topics are sorted chronologically by timestamp across all batches.

    Args:
        batches (list): List of batch entries
        batch_summaries (list): List of batch summaries
        video_id (str): Panopto video ID
        html_file (str): Output HTML file path
        transcript_data (list, optional): Full transcript data for better timestamp matching

    Returns:
        str: Path to the generated HTML file
    """
    html_content = "<!DOCTYPE html>\n<html>\n<head>\n<title>Meeting Summaries</title>\n"
    html_content += "<style>\n"
    html_content += "body { font-family: Arial, sans-serif; margin: 20px; font-size: 11pt; }\n"
    html_content += "ol { list-style-position: outside; padding-left: 12px; margin-top: 2px; }\n"
    html_content += "ol li { margin-bottom: 1px; }\n"
    html_content += ".topic-content { margin-bottom: 0px; font-family: Arial, sans-serif; font-size: 11pt; margin-top: 0px; display: inline; }\n"
    # Title styling - Cambria, 11pt, #c0504d, underlined
    html_content += "h1 { font-family: Cambria, serif; font-size: 11pt; color: #c0504d; text-decoration: underline; margin-bottom: 0px; margin-top: 0px; display: inline-block; }\n"
    html_content += ".url-line { color: #1155cc; text-decoration: none; font-size: 11pt; margin-top: 2px; margin-bottom: 2px; display: block; }\n"
    # Topic styling - Arial, 11pt, #7030a0, underlined
    html_content += "h3.topic-heading { font-family: Arial, sans-serif; font-size: 11pt; color: #7030a0; text-decoration: underline; margin-top: 0px; margin-bottom: 1px; display: inline; }\n"
    html_content += "a { color: inherit; }\n"
    html_content += ".topic-link { text-decoration: underline; color: #7030a0; }\n"
    html_content += ".topic-link span { text-decoration: underline; }\n"
    html_content += "b { font-weight: bold; }\n"
    html_content += "</style>\n</head>\n<body>\n"

    try:
        folder_name = os.path.basename(os.path.dirname(html_file))
        formatted_name = _format_meeting_name(folder_name)
        html_content += f'<h1>{formatted_name}</h1>\n'
    except:
        html_content += "<h1>Meeting Summary</h1>\n"

    if video_id:
        video_link = f"https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id={video_id}"
        html_content += f'<a href="{video_link}" class="url-line">{video_link}</a>\n'

    # Extract all topics from all batches
    all_topics = []

    for i, (batch, summary) in enumerate(zip(batches, batch_summaries), 1):
        # Extract topics from the summary with their timestamps
        topics = extract_topics_from_summary(summary, video_id, transcript_data)

        # If we have transcript data, update the topic timestamps to better match content
        if transcript_data:
            topics = update_speaker_timestamps_for_topics(topics, transcript_data)

        # Add batch index for reference
        for topic in topics:
            topic["batch_index"] = i
            topic["batch"] = batch

        all_topics.extend(topics)

    # Sort all topics by timestamp_seconds
    all_topics.sort(
        key=lambda x: (
            x["timestamp_seconds"]
            if x["timestamp_seconds"] is not None
            else float("inf")
        )
    )

    # Generate HTML content with ordered list
    html_content += "<ol>\n"

    # Process each topic
    for idx, topic_info in enumerate(all_topics, 1):
        topic = topic_info["topic"]
        speaker = topic_info["speaker"]
        content = topic_info["content"]

        html_content += '<li><h3 class="topic-heading">'

        # Check if the topic has a direct timestamp link
        if topic_info["video_link"] and topic_info["timestamp_seconds"] is not None:
            # Use the direct link from the timestamp in the summary
            topic_link = topic_info["video_link"]
            seconds = topic_info["timestamp_seconds"]

            # Verify the timestamp matches the seconds value
            # If not, get a corrected timestamp
            corrected_timestamp = verify_timestamp_format(
                topic_info["timestamp"], seconds
            )

            html_content += f'<a href="{topic_link}" class="topic-link">'
            html_content += f'{topic} - {speaker} <span style="color: #1155cc;">({corrected_timestamp})</span></a>'
        else:
            # Fallback: Find the entry for this speaker in the batch
            names = re.split(r'\s*&\s*|,\s*| and ', speaker)
            speaker_entry = None
            for entry in topic_info["batch"]:
                if entry["name"] in names:
                    speaker_entry = entry
                    break

            # If we found the entry, create a link to it
            if speaker_entry:
                speaker_seconds = speaker_entry["seconds"]
                speaker_time = verify_timestamp_format(
                    speaker_entry.get("time_str", ""), speaker_seconds
                )
                topic_link = f"https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id={video_id}&start={speaker_seconds}"

                html_content += f'<a href="{topic_link}" class="topic-link">'
                html_content += f'{topic} - {speaker} <span style="color: #1155cc;">({speaker_time})</span></a>'
            else:
                # If no entry found, just display the topic without a link
                html_content += f'{topic} - {speaker}'

        html_content += '</h3>: '  # Colon and space before content
        html_content += f'<div class="topic-content">{content}</div></li>\n'

    html_content += "</ol>\n</body>\n</html>"

    # Write the file
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Generated meeting summaries HTML with verified timestamps: {html_file}")
    return html_file

def _format_meeting_name(raw_name: str) -> str:
    """Format meeting name for display in HTML/Markdown."""
    import re
    
    # Replace underscores with spaces
    formatted = raw_name.replace('_', ' ')
    
    # Fix timestamp formatting (e.g., "4.00pm" -> "4:00pm")
    formatted = re.sub(r'(?<=\d)\.(\d{2})(am|pm)', r':\1\2', formatted)
    
    return formatted

def generate_meeting_summaries_markdown(
    batches, batch_summaries, video_id, md_file, transcript_data=None
):
    """
    Generate Markdown file with meeting batch summaries that include clickable timestamp links
    (if video_id provided) or text-only timestamps.
    Topics are sorted chronologically by timestamp, and timestamps are verified to match URL seconds.

    Args:
        batches (list): List of batch entries
        batch_summaries (list): List of batch summaries
        video_id (str): Panopto video ID (can be None for text-only timestamps)
        md_file (str): Output Markdown file path
        transcript_data (list, optional): Full transcript data for better timestamp matching

    Returns:
        str: Path to the generated Markdown file
    """
    md_lines = []
    try:
        title = re.sub(r'(?<=\d)\.(\d{2})(am|pm)', r':\1\2', md_file)
        folder_name = os.path.basename(os.path.dirname(title))
        formatted_name = folder_name.replace("_", " ")
        
        if video_id:
            video_link = f"https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id={video_id}"
            md_lines.append(f"# [{formatted_name}]({video_link})\n")
        else:
            md_lines.append(f"# {formatted_name}\n")
    except:
        md_lines.append("# Meeting Summary\n")
        
    # Extract all topics from all batches
    all_topics = []

    for i, (batch, summary) in enumerate(zip(batches, batch_summaries), 1):
        # Extract topics from the summary with their timestamps
        topics = extract_topics_from_summary(summary, video_id, transcript_data)

        # If we have transcript data, update the topic timestamps to better match content
        if transcript_data:
            topics = update_speaker_timestamps_for_topics(topics, transcript_data)

        # Add batch index for reference
        for topic in topics:
            topic["batch_index"] = i
            topic["batch"] = batch

        all_topics.extend(topics)

    # Sort all topics by timestamp_seconds
    all_topics.sort(
        key=lambda x: (
            x["timestamp_seconds"]
            if x["timestamp_seconds"] is not None
            else float("inf")
        )
    )

    # Process each topic
    for topic_info in all_topics:
        topic = topic_info["topic"]
        speaker = topic_info["speaker"]
        content = topic_info["content"]
        batch = topic_info["batch"]

        # Check if the topic has a direct timestamp link and video_id is provided
        if video_id and topic_info["video_link"] and topic_info["timestamp_seconds"] is not None:
            # Use the direct link from the timestamp in the summary
            topic_link = topic_info["video_link"]
            seconds = topic_info["timestamp_seconds"]

            # Verify the timestamp matches the seconds value
            corrected_timestamp = verify_timestamp_format(
                topic_info["timestamp"], seconds
            )

            # Add topic as a subheading with direct link and corrected timestamp
            md_lines.append(
                f"**{topic} - {speaker}** [({corrected_timestamp})]({topic_link})"
            )
        elif video_id:
            # Fallback: Find the entry for this speaker in the batch with video links
            speaker_entry = None
            for entry in batch:
                if entry["name"] == speaker:
                    speaker_entry = entry
                    break

            # If we found the entry, create a link to it
            if speaker_entry:
                speaker_seconds = speaker_entry["seconds"]
                speaker_time = verify_timestamp_format(
                    speaker_entry.get("time_str", ""), speaker_seconds
                )
                topic_link = f"https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id={video_id}&start={speaker_seconds}"

                # Add topic as a subheading with link from entry
                md_lines.append(
                    f"**{topic} - {speaker}** [({speaker_time})]({topic_link})"
                )
            else:
                # If no entry found, just display the topic without a link
                md_lines.append(f"**{topic} - {speaker}**")
        else:
            # No video_id provided - use text-only timestamps
            if topic_info["timestamp_seconds"] is not None:
                corrected_timestamp = verify_timestamp_format(
                    topic_info["timestamp"], topic_info["timestamp_seconds"]
                )
                md_lines.append(f"**{topic} - {speaker}** ({corrected_timestamp})")
            else:
                # Find timestamp from batch entry
                speaker_entry = None
                for entry in batch:
                    if entry["name"] == speaker:
                        speaker_entry = entry
                        break
                
                if speaker_entry:
                    speaker_time = verify_timestamp_format(
                        speaker_entry.get("time_str", ""), speaker_entry["seconds"]
                    )
                    md_lines.append(f"**{topic} - {speaker}** ({speaker_time})")
                else:
                    md_lines.append(f"**{topic} - {speaker}**")

        # Add the content for this topic
        md_lines.append(f"{content}\n")

    # Write the file
    with open(md_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    timestamp_type = "clickable links" if video_id else "text-only timestamps"
    print(f"Generated meeting summaries markdown with {timestamp_type}: {md_file}")
    return md_file


def summarize_batch(batch_entries, batch_number, api_key):
    """
    Summarize a batch of transcript entries using OpenAI API

    Args:
        batch_entries (list): List of transcript entries for this batch
        batch_number (int): Batch number for identification
        api_key (str): OpenAI API key

    Returns:
        str: Batch summary with topics and timestamps
    """
    if not api_key:
        return "API key not provided. Summaries not generated."

    # Extract batch text
    batch_text = extract_text_for_batch(batch_entries)

    if not batch_text.strip():
        return "No text available for summarization."

    # Get start and end times
    start_seconds = min(entry["seconds"] for entry in batch_entries)
    # End time is either explicit end_seconds or last entry
    if any("end_seconds" in entry for entry in batch_entries):
        # Use the max end_seconds if available
        end_seconds = max(
            entry.get("end_seconds", entry["seconds"]) for entry in batch_entries
        )
    else:
        # Otherwise use the last entry in the batch
        end_seconds = max(entry["seconds"] for entry in batch_entries)

    start_time = seconds_to_time_str(start_seconds)
    end_time = seconds_to_time_str(end_seconds)

    try:
        openai.api_key = api_key
         # Determine if this is the first batch (meeting start)
        is_first_batch = batch_number == 1
        
        base_prompt = f"""
        You are a meeting summarization assistant . 
        You are given a batch of transcript text from a meeting along with detailed speaker timestamps.
        Your task is to act as a technical summarizer who identifies key topics discussed in the meeting batch,
        assigns each topic to the appropriate speaker(s), and provides concise summaries for each topic.
        You must follow the instructions below to ensure accurate timestamp usage and content summarization.
        Your style should be formal, technical, and objective , using third-person phrasing.
        
        ## INPUT :
        - MEETING TRANSCRIPT BATCH TEXT: The transcript text for the current batch of the meeting.
        - SPEAKER TIMESTAMPS: A detailed list of timestamps for each speaker in the batch, including context snippets.

        ## TASK AND CONSTRAINTS
        
        CONTENT MINING:
        1. Identify distinct topics discussed in the batch text.
        2. For each topic, determine the primary speaker(s) involved.
        3. Find adjacent text segments from the speaker(s) that relate to the topic.
        4. Define the interval during which the topic was discussed.
        5. Assign the MOST RELEVANT timestamp from SPEAKER TIMESTAMPS to each topic based on when the topic was discussed.
        6. Summarize each topic in a detailed manner, focusing on technical details, decisions, and action items.
        7. Ensure all topics are covered, even if briefly mentioned.        

        CONTENT REQUIREMENTS:

        ## 1. MINING :
        - The current text must be paraphrased, ensure maximum detailed coverage of all topics discussed.
        - Summarize each topic in a detailed manner, focusing on technical details, decisions, and action items.
        - The topics might be generic , technical , or social in nature - ensure all topics are captured.
        - Provide the whole spectrum of the topic as discussed by the speaker(s) through the time interval.
        - Ignore noise such as "[music]", "[applause]", "[inaudible]" , your task is to summarize meaningful content only.
        - Use the exact timestamps provided in SPEAKER TIMESTAMPS.
        - The text must include interactions between speakers when relevant . Example : ... [Speaker A] ... [X] , while [Speaker B] ... [Y] ...
        - Some topics may have more detail than others, ensure all topics are covered.
        - Multiple speakers may discuss the same topic; list all relevant speakers.
        
        ## 2. FORMATTING :
        
        ### GENERAL
        - Present the output in JSON format as specified below.
        - Each topic must have a title, list of speakers, assigned timestamp, and detailed summary.
        - Titles should be concise yet descriptive of the topic discussed.
        - Use <b>...</b> tags to bold important terms in the summaries.
        - Important terms include technical terms, decisions, action items, and key concepts.
        - Ensure proper JSON syntax without deviations.
        
        ### WRITING STYLE
        {'- You MUST begin with the first topical content **even if it is lightweight** (greetings, agenda, setup).' if is_first_batch else ''}
        {'- If the earliest content is simple, title it: "Introductions & Setup"' if is_first_batch else ''}
        - Capture the timeline of the discussion of the topics as accurately as possible.
        - Contain the whole spectrum of the topic discussed by the speaker(s) through the time interval.
        - A topic may be generic , technical , or social in nature - ensure all topics are captured.
        - Write in Third Person; Paraphrase; do NOT copy from the transcript.
        - Do not include first person phrasing (no "I/We/You…"). Do not replicate dialogue format.
        - Avoid proper nouns unless needed for clarity (use roles when possible).
        - If the discussion is light or social, still include it as a topic but summarize accordingly.
        
        ### CONTENT CLARIFICATIONS
        - The text is produced from a software recording of a meeting, there might be discrepencies in technical terms, fix them when possible.
        - The software may mispell technical terms, correct them when possible.
        - Do NOT fabricate content, only summarize what is present in the transcript text.
        - Do NOT omit any topics, even if they seem minor.
        - Focus on technical details, decisions, action items, and key concepts , bold important terms using <b>...</b> tags.
        - The tone of the summary changes based on the content - it can be formal, technical, or casual as needed.

        TIMESTAMP RULES:
        - For each topic, choose the MOST RELEVANT timestamp from SPEAKER TIMESTAMPS for the speaker actually discussing that topic.
        - The FIRST topic MUST use the earliest timestamp from this batch window: {start_time} - {end_time} .
        - Subsequent topics should use timestamps that are as close as possible to when the topic was discussed.
        - If a topic is discussed by multiple speakers, choose the earliest timestamp among them.
        - If a topic spans multiple timestamps, choose the timestamp that best represents when the topic began.
        - If a topic is only briefly mentioned, still assign the closest relevant timestamp.
        - Never create, edit, or infer a timestamp. They are going to be used as clickable links later.
        - Use the exact format (H:MM:SS) for timestamps.

        ## OUTPUT :
        ```json
        {'''
            "results": {
                "<Topic 1> : {
                    "speakers": ["<Speaker_Name>" , ...],
                    "timestamp": "(H:MM:SS)",
                    "summary": "<Concise_summary_of_the_topic_discussed>",
                    "type": "<Topic_Type>"
                },
                ...
                "<Topic N>": {
                    "speakers": ["<Speaker_Name>" , ...],
                    "timestamp": "(H:MM:SS)",
                    "summary": "<Concise_summary_of_the_topic_discussed>",
                    "type": "<Topic_Type>"
                }
            }
        '''}
        ```

        Remember to strictly follow the JSON format above without deviation.
        """

        # Using chat completions API
        response = openai.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": base_prompt,
                },
                {"role": "user", "content":  
                    f"""
                    I am providing you with the transcript text for batch #{batch_number} (timespan: {start_time} - {end_time}) below:
                    {batch_text}
                    \n\n
                    Your task is to summarize the batch text into distinct topics as per the instructions given.
                    The current batch contains {len(batch_entries)} speaker entries amd it is a part of a larger meeting for the Mantis AI platform.
                    Mantis AI is a platform developed and maintained by MIT's Kellis Lab , and it is focused on cognitive data science and data cartography.
                    Please provide the summary in the specified JSON format.                    
                    """},
            ],
            max_tokens=10000,  # More tokens for batch summaries
        )
        
        # format the response to be a list of lines of the form : **<Topic_Title> - <Speaker_Name> , ... , <Speaker_Name>** (H:MM:SS) : <Summary_Content>
        # 1. Extract the text content from the response
        summary_text = response.choices[0].message.content.strip()
        # 2. Extract JSON part from the response
        return parse_json(summary_text)

    except Exception as e:
        return f"Error generating batch summary: {str(e)}"


# -------------------------------------------------------------
# Main Processing Function
# -------------------------------------------------------------
"""
Optimized speaker summary generation integration for xlsx2html.py
"""

# Update the process_xlsx function in xlsx2html.py to use the optimized approach:

def generate_mantis_excel(batches, batch_summaries, video_id, output_file, transcript_data=None):
    """
    Generate an Excel file formatted for MantisAPI ingestion.
    Columns: Title, Speaker, Time, Seconds, Content, Link
    """
    all_topics = []
    for i, (batch, summary) in enumerate(zip(batches, batch_summaries), 1):
        topics = extract_topics_from_summary(summary, video_id, transcript_data)
        if transcript_data:
            topics = update_speaker_timestamps_for_topics(topics, transcript_data)
        all_topics.extend(topics)
    
    # Sort by timestamp
    all_topics.sort(key=lambda x: (x["timestamp_seconds"] if x["timestamp_seconds"] is not None else float("inf")))

    data = []
    for t in all_topics:
        data.append({
            "Title": t['topic'],
            "Speaker": t['speaker'],
            "Time": t['timestamp'] if t['timestamp'] else "00:00:00",
            "Seconds": t['timestamp_seconds'] if t['timestamp_seconds'] is not None else 0,
            "Content": t['content'],
            "Link": t['video_link'] if t['video_link'] else ""
        })
    
    df = pd.DataFrame(data)
    # Reorder columns to ensure consistency with MantisAPI mapping
    df = df[["Title", "Speaker", "Time", "Seconds", "Content", "Link"]]
    
    df.to_excel(output_file, index=False)
    logger.info(f"Generated Mantis import file: {output_file}")
    return output_file

def process_xlsx(
    xlsx_file,
    video_id,
    html_file=None,
    speaker_summary_file=None,
    meeting_summary_md_file=None,
    batch_size_minutes=DEFAULT_BATCH_SIZE_MINUTES,
    use_enhanced_summaries=False,
):
    """
    Process Excel file to generate HTML links with summaries and meeting summaries

    Args:
        xlsx_file (str): Path to input Excel file
        video_id (str): Panopto video ID (can be None for text-only timestamps)
        html_file (str, optional): Path to output HTML file for speaker links
        speaker_summary_file (str, optional): Path to output Markdown file for speaker summaries
        meeting_summary_md_file (str, optional): Path to output Markdown file for meeting summaries
        batch_size_minutes (int, optional): Batch size in minutes (default: DEFAULT_BATCH_SIZE_MINUTES)
        use_enhanced_summaries (bool, optional): Whether to use enhanced speaker summaries

    Returns:
        tuple: Paths to the generated files (html_file, summary_file, speaker_summary_file, meeting_summary_md_file)
    """
    if html_file is None:
        html_file = os.path.splitext(xlsx_file)[0] + "_speaker_summaries.html"

    if speaker_summary_file is None:
        speaker_summary_file = os.path.splitext(xlsx_file)[0] + "_speaker_summaries.md"

    summary_file = os.path.splitext(xlsx_file)[0] + "_meeting_summaries.html"

    if meeting_summary_md_file is None:
        meeting_summary_md_file = (
            os.path.splitext(xlsx_file)[0] + "_meeting_summaries.md"
        )
    
    # Define the Mantis output file path
    mantis_file = os.path.splitext(xlsx_file)[0] + "_mantis.xlsx"

    # Get OpenAI API key
    api_key = get_api_key()
    if not api_key:
        logger.warning("OpenAI API key not provided. Summaries will not be generated.")
        return None, None, None, None

    try:
        # Read the Excel file
        
        df = pd.read_excel(xlsx_file)
        logger.info(f"Read Excel file: {xlsx_file}")
        # Extract speaker links
        speaker_links = extract_unique_speakers(df)
        logger.info(f"Extracted {len(speaker_links)} unique speakers")

        # Extract full transcript data
        transcript_data = extract_transcript_data(df)
        logger.info(f"Extracted transcript data with {len(transcript_data)} entries")

        # Use enhanced speaker summaries if requested and available
        #if use_enhanced_summaries and ENHANCED_SUMMARIES_AVAILABLE:
        #    link_type = "clickable links" if video_id else "text-only timestamps"
        #    logger.info(f"Using enhanced speaker summaries with multiple topic support and {link_type}...")
        #    # Generate summaries data once - this avoids duplicate API calls
        #    logger.info("Generating speaker topic summaries...")
        #    summaries_data = generate_speaker_summaries_data(transcript_data, api_key)
        #    # Generate enhanced speaker summary markdown
        #    if speaker_summary_file:
        #        logger.info(f"Generating enhanced speaker summary Markdown: {speaker_summary_file}")
        #        generate_enhanced_speaker_summary_markdown(
        #            transcript_data,
        #            video_id,  # Can be None
        #            speaker_summary_file,
        #            api_key,
        #            summaries_data,  # Pass the pre-generated summaries
        #        )
        #        logger.info(f"Generated enhanced speaker summary Markdown: {speaker_summary_file}")
        #    # Generate enhanced speaker summary HTML
        #    if html_file:
        #        logger.info(f"Generating enhanced speaker summary HTML: {html_file}")
        #        generate_enhanced_speaker_summary_html(
        #            transcript_data,
        #            video_id,  # Can be None
        #            html_file,
        #            api_key,
        #            summaries_data,  # Pass the pre-generated summaries
        #        )
        #        print(f"Generated enhanced speaker summary HTML: {html_file}")
        #
        # Create time-based batches directly from transcript data
        logger.info("Creating time-based batches for meeting summaries...")
        #batches = create_time_batches(transcript_data, batch_size_minutes)
        batches = create_time_batches(transcript_data, batch_size_minutes, use_smart_batching=True)
        logger.info(f"Created {len(batches)} batches")
        
        # Generate batch summaries
        batch_summaries = []
        for i, batch in enumerate(batches, 1):
            # Get start and end times for this batch
            start_seconds = min(entry["seconds"] for entry in batch)
            # End time is either explicit end_seconds or last entry
            if any("end_seconds" in entry for entry in batch):
                end_seconds = max(
                    entry.get("end_seconds", entry["seconds"]) for entry in batch
                )
            else:
                end_seconds = max(entry["seconds"] for entry in batch)

            start_time = seconds_to_time_str(start_seconds)
            end_time = seconds_to_time_str(end_seconds)

            logger.info(f"Processing batch {i}/{len(batches)}: {start_time} - {end_time}")

            # Generate summary
            summary = summarize_batch(batch, i, api_key)
            batch_summaries.append(summary)

        logger.info(f"Generating Mantis import file: {mantis_file}")
        generate_mantis_excel(batches, batch_summaries, video_id, mantis_file, transcript_data)

        # Generate meeting summaries HTML with topic-level clickable links (or text-only timestamps)
        # Pass transcript_data for improved timestamp matching
        logger.info(f"Generating meeting summaries HTML: {summary_file}")
        generate_meeting_summaries_html(
            batches, batch_summaries, video_id, summary_file, transcript_data
        )
        timestamp_type = "clickable links" if video_id else "text-only timestamps"
        logger.info(f"Generated meeting summaries HTML with {timestamp_type}: {summary_file}")
        # Generate meeting summaries Markdown with topic-level clickable links (or text-only timestamps)
        # Pass transcript_data for improved timestamp matching
        generate_meeting_summaries_markdown(
            batches, batch_summaries, video_id, meeting_summary_md_file, transcript_data
        )
        print(f"Generated meeting summaries Markdown with {timestamp_type}: {meeting_summary_md_file}")

        # Return 5 files now instead of 4
        return html_file, summary_file, speaker_summary_file, meeting_summary_md_file, mantis_file

    except Exception as e:
        print(f"Error processing Excel file: {e}", file=sys.stderr)
        raise


def main():
    """
    Main function to handle command-line arguments and process Excel file
    """
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description="Convert Excel transcript to HTML links with summaries"
    )
    parser.add_argument("input_file", help="Input Excel file")
    parser.add_argument("video_id", help="Panopto video ID (required)")
    parser.add_argument("output_file", nargs="?", help="Output HTML file (optional)")
    parser.add_argument(
        "--summary-file", help="Output file for meeting summaries HTML (optional)"
    )
    parser.add_argument(
        "--speaker-summary-file",
        help="Output file for speaker summaries markdown (optional)",
    )
    parser.add_argument(
        "--meeting-summary-md-file",
        help="Output file for meeting summaries markdown (optional)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE_MINUTES,
        help=f"Batch size in minutes (default: {DEFAULT_BATCH_SIZE_MINUTES})",
    )
    parser.add_argument(
        "--enhanced-summaries",
        action="store_true",
        help="Generate enhanced speaker summaries with multiple topics (requires speaker_summary_utils.py)",
    )

    args = parser.parse_args()

    # Check if enhanced summaries are requested but not available
    if args.enhanced_summaries and not ENHANCED_SUMMARIES_AVAILABLE:
        print(
            "Warning: Enhanced speaker summaries requested but speaker_summary_utils.py is not available."
        )
        print("Falling back to traditional speaker summaries.")
        args.enhanced_summaries = False

    try:
        html_file, summary_html_file, speaker_summary_file, meeting_summary_md_file = (
            process_xlsx(
                args.input_file,
                args.video_id,
                args.output_file,
                args.speaker_summary_file,
                args.meeting_summary_md_file,
                args.batch_size,
                args.enhanced_summaries,
            )
        )

        if html_file and summary_html_file:
            print(f"Processing complete!")
            print(f"Speaker links HTML: {html_file}")
            print(f"Speaker summary Markdown: {speaker_summary_file}")
            print(f"Meeting summaries HTML: {summary_html_file}")
            print(f"Meeting summaries Markdown: {meeting_summary_md_file}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
