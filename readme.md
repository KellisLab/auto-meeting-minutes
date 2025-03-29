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

- Python 3.6 or higher
- pip (Python package installer)

### Setting Up the Environment

1. **Clone the repository**

```bash
git clone https://github.com/KellisLab/auto-meeting-minutes.git
```

2. **Create and activate a virtual environment**

For Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

For macOS/Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

or

```bash
pip install pandas openpyxl numpy requests openai python-dotenv beautifulsoup4 scikit-learn nltk
```

4. **Set up OpenAI API key**

Create a `.env` file in the project directory:

```
API_KEY=your_openai_key_here
GPT_MODEL="chatgpt-4o-latest"  # or another available model
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

## Troubleshooting

### Common Issues

1. **Missing dependencies**: If you encounter import errors, ensure all dependencies are installed:
   ```bash
   pip install -r requirements.txt
   ```

2. **NLTK resource errors**: If refineStartTimes.py raises errors about missing NLTK resources:
   ```bash
   python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"
   ```

3. **OpenAI API errors**: Verify your API key is correctly set and has sufficient credits.

4. **SRT download failures**: Ensure the Panopto URL is correct and the video has available transcripts.

### Debugging Tips

- Run each component separately to isolate issues
- Check intermediate files (.srt, .txt, .xlsx) for content validity
- Enable verbose output with the `--verbose` flag where available
- Look for error messages in the console output

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
- Create a web interface for easier access

## License

This project is available under the MIT License.

## Contributors

This pipeline was developed to help process and analyze video content efficiently.