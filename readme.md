# Video Transcript Processing Pipeline

A comprehensive pipeline for processing video transcripts from Panopto URLs to structured, searchable formats with AI-generated summaries. This toolset converts subtitles to text, Excel, and HTML formats with direct video timestamp links and intelligent content summaries.

## Overview

This pipeline integrates several Python scripts to create a complete workflow:

1. **url2id.py** - Extract Panopto video ID from a URL
2. **url2file.py** - Download SRT transcript from Panopto using video ID
3. **vtt2txt.py** - Convert subtitles (VTT/SRT) to plain text transcripts with timestamps
4. **txt2xlsx.py** - Convert text to Excel with speaker highlighting and visual formatting
5. **xlsx2html.py** - Convert Excel to HTML with direct timestamp links and AI-generated summaries
6. **fullpipeline.py** - Run the entire process from URL to HTML summaries in one command

## Requirements

- Python 3.6+
- Required packages:
  ```
  pandas
  openpyxl
  numpy
  requests
  openai
  python-dotenv
  ```

Install requirements:

```bash
pip install pandas openpyxl numpy requests openai python-dotenv
```

## Quick Start

Use the integrated pipeline script to process a Panopto video in one command:

```bash
python fullpipeline.py https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id=YOURVIDEOID
```

This will:
1. Extract the video ID from the URL
2. Download the transcript as SRT
3. Convert to plain text
4. Format as Excel
5. Generate HTML with direct links and AI summaries

## Pipeline Components

### 1. URL to ID (url2id.py)

Extracts the Panopto video ID from a URL.

```bash
python url2id.py [url]
```

Example:
```bash
python url2id.py https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id=ef5959d0-da5f-4ac0-a1ad-b2aa001320a0
# Output: ef5959d0-da5f-4ac0-a1ad-b2aa001320a0
```

### 2. URL to File (url2file.py)

Downloads a subtitle file in SRT format from a Panopto URL.

```bash
python url2file.py [url] [output_file]
```

Example:
```bash
python url2file.py https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id=ef5959d0-da5f-4ac0-a1ad-b2aa001320a0 lecture.srt
```

Supports language selection with `--language` option (default: "English_USA").

### 3. VTT to TXT (vtt2txt.py)

Converts WebVTT/SRT subtitle files to plain text transcripts with timestamps.

```bash
python vtt2txt.py input.vtt [output.txt]
```

Output format:
```
00:00:10 Speaker Name: Text content
00:00:15 Another Speaker: More text content
```

### 4. TXT to XLSX (txt2xlsx.py)

Converts text transcripts to formatted Excel files with color-coding for speakers.

```bash
python txt2xlsx.py input.txt [output.xlsx]
```

Features:
- Color-coded speakers (unique color per speaker)
- Rainbow time gradient for timestamps
- Special tracking of first speaker occurrences
- Auto-adjusted column widths

### 5. XLSX to HTML (xlsx2html.py)

Converts Excel transcript files to HTML with video links and AI-generated summaries.

```bash
python xlsx2html.py input.xlsx VIDEO_ID [output.html] [--format={simple|numbered}]
```

Features:
- Creates direct links to video timestamps for all speakers
- Identifies segments between consecutive timestamps
- Generates AI-powered summaries for each segment using OpenAI API
- Creates batch summaries for longer segments of content
- Outputs both HTML and Markdown formats

Output files:
- `*_speaker_summaries.html` - HTML with speaker links and summaries
- `*_meeting_summaries.html` - HTML with batch summaries and topic links
- `*_speaker_summaries.md` - Markdown version of speaker summaries
- `*_meeting_summaries.md` - Markdown version of meeting summaries

### 6. Full Pipeline (fullpipeline.py)

Runs the entire process from URL to HTML summaries in one command.

```bash
python fullpipeline.py [url] [--skip-refinement] [--html-format={simple|numbered}] [--language LANGUAGE]
```

Options:
- `--skip-refinement`: Skip the start time refinement step (placeholder for future implementation)
- `--html-format`: Choose between "simple" or "numbered" HTML output format
- `--language`: Language code for transcript (default: "English_USA")

## OpenAI API Key Configuration

For the summarization features to work, an OpenAI API key is required. The script will look for it in:

1. Environment variable `OPENAI_API_KEY`
2. The constant `OPENAI_API_KEY` in xlsx2html.py
3. A file at `~/.openai_config`
4. A `.env` file in the current directory with:
   ```
   API_KEY=your_key_here
   GPT_MODEL=gpt-4o  # or other model
   ```

You can also enter the key interactively when prompted.

## Customization

Various parameters can be adjusted:

- In txt2xlsx.py: Color generation, column formatting
- In xlsx2html.py: 
  - Batch size for summaries (`BATCH_SIZE_SECONDS`)
  - AI model selection (via `.env` file)
  - Summary prompt templates
  - HTML and Markdown formatting

## Output Files

For a video with ID `meeting`, the pipeline produces:
- `meeting.srt` - Original subtitle file
- `meeting.txt` - Plain text transcript
- `meeting.xlsx` - Excel formatted transcript
- `meeting_speaker_summaries.html` - HTML with speaker links
- `meeting_meeting_summaries.html` - HTML with batch summaries
- `meeting_speaker_summaries.md` - Markdown speaker summaries
- `meeting_meeting_summaries.md` - Markdown meeting summaries

## Future Improvements

- Implement actual refinement logic in refineStartTimes.py
- Add support for different video platforms beyond Panopto
- Improve AI summarization with more advanced prompts
- Add alternative summary methods that don't require OpenAI
- Implement speech-to-text options for videos without existing subtitles
- Create a web interface for easier access

## License

This project is available under the MIT License.

## Contributors

This pipeline was developed to help process and analyze video content efficiently.