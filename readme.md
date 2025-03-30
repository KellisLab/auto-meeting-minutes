# Video Transcript Processing Pipeline

A comprehensive pipeline for processing video transcripts from Panopto URLs to structured, searchable formats with AI-generated summaries. This toolset converts subtitles to text, Excel, and HTML formats with direct video timestamp links and intelligent content summaries.

## Overview

This pipeline integrates several Python scripts to create a complete workflow:

1. **url2id.py** - Extract Panopto video ID from a URL
2. **url2file.py** - Download SRT transcript from Panopto using video ID
3. **vtt2txt.py** - Convert subtitles (VTT/SRT) to plain text transcripts with timestamps
4. **txt2xlsx.py** - Convert text to Excel with speaker highlighting and visual formatting
5. **refineStartTimes.py** - Improve timestamp matching for speakers with multiple appearances
6. **xlsx2html.py** - Convert Excel to HTML with direct timestamp links and AI-generated summaries
7. **fullpipeline.py** - Run the entire process from URL to HTML summaries in one command

## Setup and Installation

### Prerequisites

- Python 3.12 or higher
- pip (Python package installer)
- Docker

### Setting Up the Environment

1. **Clone the repository**

```bash
git clone https://github.com/KellisLab/auto-meeting-minutes.git
```

2. **Add .env file**

Create a `.env` file in the project directory:

```
API_KEY=your_openai_key_here
GPT_MODEL="chatgpt-4o-latest"  # or another available model
```

3. **Docker**
```bash
docker compose up
```

Access the web interface at http://localhost:5001

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

### 5. Refine Start Times (refineStartTimes.py)

Improves timestamp matching for speakers who appear multiple times, ensuring topics in summaries link to the correct instances.

```bash
python refineStartTimes.py input.xlsx [output.xlsx]
```

Features:
- Analyzes text content for better topic-to-timestamp matching
- Uses natural language processing to find the most relevant speaker instances
- Updates Excel with improved timestamp mappings
- Can post-process summaries to improve timestamp accuracy
- Generates corrected markdown files with accurate timestamps

### 6. XLSX to HTML (xlsx2html.py)

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

### 7. Full Pipeline (fullpipeline.py)

Runs the entire process from URL to HTML summaries in one command.

```bash
python fullpipeline.py [url] [--skip-refinement] [--html-format={simple|numbered}] [--language LANGUAGE]
```

Options:
- `--skip-refinement`: Skip the start time refinement step
- `--html-format`: Choose between "simple" or "numbered" HTML output format
- `--language`: Language code for transcript (default: "English_USA")

## Customization

Various parameters can be adjusted:

- In txt2xlsx.py: Color generation, column formatting
- In refineStartTimes.py:
  - Text similarity thresholds
  - Keyword extraction settings
  - Maximum time gap for matching
- In xlsx2html.py: 
  - Batch size for summaries (`DEFAULT_BATCH_SIZE_MINUTES`)
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

- Enhance refineStartTimes.py with more advanced text matching algorithms
- Add support for different video platforms beyond Panopto
- Improve AI summarization with more advanced prompts
- Add alternative summary methods that don't require OpenAI
- Implement speech-to-text options for videos without existing subtitles

## License

This project is available under the MIT License.

## Contributors

This pipeline was developed to help process and analyze video content efficiently.