# Video Transcript Processing Pipeline

This pipeline processes video subtitles from VTT format to structured HTML summaries and links. It integrates several scripts to handle the conversion process:

1. **vtt2txt.py** - Convert WebVTT subtitle files to plain text transcripts with timestamps
2. **txt2xlsx.py** - Convert plain text transcripts to Excel format with speaker highlighting
3. **refineStartTimes.py** - Refine speaker start times (placeholder for future implementation)
4. **xlsx2html.py** - Convert Excel transcript files to HTML with links and AI-generated summaries

The pipeline is designed for processing meeting or lecture recordings, particularly those hosted on Panopto.

## Requirements

- Python 3.6+
- Required packages:
  - pandas
  - openpyxl
  - numpy
  - openai (if using summarization features)
  - dotenv (for loading API keys)

Install requirements:

```bash
pip install pandas openpyxl numpy openai python-dotenv
```

## Quick Start

Use the integrated pipeline script to process a VTT file in one command:

```bash
python transcript_pipeline.py input.vtt VIDEO_ID
```

Where `VIDEO_ID` is the Panopto video identifier (looks like a UUID/GUID).

## Pipeline Components

### 1. VTT to TXT (vtt2txt.py)

Converts WebVTT subtitle files to plain text transcripts with timestamps.

```bash
python vtt2txt.py input.vtt [output.txt]
```

Output format:
```
00:00:10 Speaker Name: Text content
00:00:15 Another Speaker: More text content
```

### 2. TXT to XLSX (txt2xlsx.py)

Converts text transcripts to formatted Excel files with color-coding for speakers.

```bash
python txt2xlsx.py input.txt [output.xlsx]
```

Features:
- Color-coded speakers
- Rainbow gradient for timestamps
- Tracking first occurrences of each speaker

### 3. Refine Start Times (refineStartTimes.py)

Placeholder for refining speaker start times in the Excel file. Currently outputs the file unchanged.

```bash
python refineStartTimes.py input.xlsx [output.xlsx]
```

### 4. XLSX to HTML (xlsx2html.py)

Converts Excel transcript files to HTML with video links and AI-generated summaries.

```bash
python xlsx2html.py input.xlsx VIDEO_ID [output.html] [--format={simple|numbered}]
```

Features:
- Creates direct links to video timestamps for all speakers
- Generates AI-powered summaries for segments (requires OpenAI API key)
- Creates both speaker summaries and meeting summaries

## OpenAI API Key Configuration

For the summarization features to work, an OpenAI API key is required. The script will look for it in:

1. The environment variable `OPENAI_API_KEY`
2. A file at `~/.openai_config`
3. A `.env` file in the current directory with `API_KEY=your_key_here`

You can also enter the key interactively when prompted.

## Customization

Various parameters can be adjusted:

- In txt2xlsx.py: Color generation, column formatting
- In xlsx2html.py: Batch size for summaries, AI prompt templates, HTML formatting

## Using the Integrated Pipeline

The all-in-one script integrates the entire process:

```bash
python transcript_pipeline.py input.vtt VIDEO_ID [--skip-refinement] [--html-format={simple|numbered}]
```

Options:
- `--skip-refinement`: Skip the start time refinement step
- `--html-format`: Choose between "simple" or "numbered" HTML output format

## Output Files

For an input file named `lecture.vtt`, the pipeline produces:
- `lecture.txt` - Plain text transcript
- `lecture.xlsx` - Excel formatted transcript
- `lecture.speaker_summaries.html` - HTML with speaker links and summaries
- `lecture_meeting_summaries.html` - HTML with batch summaries

## Future Improvements

- Implement actual refinement logic in refineStartTimes.py
- Add support for different video platforms beyond Panopto
- Improve AI summarization with more advanced prompts
- Add alternative summary methods that don't require OpenAI