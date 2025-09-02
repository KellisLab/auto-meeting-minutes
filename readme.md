# Video Transcript Processing Pipeline

A comprehensive toolkit for processing video transcripts from Panopto URLs, converting subtitles to structured, searchable formats with AI-generated summaries. This platform transforms closed captions into rich, navigable documents with direct video timestamp links and intelligent content summaries.

## Overview

This pipeline integrates several specialized Python scripts to create a complete workflow:

1. **url2id.py** - Extract Panopto video ID from a URL
2. **url2meeting_name.py** - Extract meeting name from Panopto URL for meaningful file naming
3. **url2file.py** - Download SRT transcript from Panopto using video ID
4. **vtt2txt.py** - Convert subtitles (VTT/SRT) to plain text transcripts with timestamps
5. **txt2xlsx.py** - Convert text to Excel with speaker highlighting and visual formatting
6. **refineStartTimes.py** - Improve timestamp matching for speakers with multiple appearances
7. **xlsx2html.py** - Convert Excel to HTML with direct timestamp links and AI-generated summaries
8. **fullpipeline.py** - Run the entire process from URL to HTML summaries in one command
9. **pipeline.py** - Process local VTT/SRT files (alternative to URL-based processing)
10. **html_bold_converter.py** - Convert markdown-style bold formatting to HTML bold tags

## Setup and Installation

### Prerequisites

- Python 3.12 or higher
- pip (Python package installer)
- OpenAI API key (for AI-generated summaries)

### Manual Installation

#### Linux/macOS

If you prefer a local installation on Linux or macOS:

1. **Clone the repository**

```bash
git clone https://github.com/KellisLab/auto-meeting-minutes.git
cd auto-meeting-minutes
```

2. **Set up a Python virtual environment**

```bash
python -m venv venv
source venv/bin/activate
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

4. **Download required NLTK data**

```bash
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('punkt_tab')"
```

5. **Create a .env file with your configuration**

```bash
echo "DJANGO_SECRET_KEY=your-secret-key-here" > .env
echo "DJANGO_DEBUG=True" >> .env
echo "DATABASE_URL=postgresql://username:password@host:port/database" >> .env
echo "PANOPTO_FOLDER_ID=your-panopto-folder-id" >> .env
```

#### Windows

For Windows users:

1. **Clone the repository**

```powershell
git clone https://github.com/KellisLab/auto-meeting-minutes.git
cd auto-meeting-minutes
```

2. **Set up a Python virtual environment**

```powershell
python -m venv venv
venv\Scripts\activate
```

3. **Install dependencies**

```powershell
pip install -r requirements.txt
```

4. **Download required NLTK data**

```powershell
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('punkt_tab')"
```

5. **Create a .env file with your configuration (using PowerShell)**

```powershell
# Create .env file with Django and database configuration
"DJANGO_SECRET_KEY = ""your-secret-key-here""" | Out-File -FilePath .env
"DJANGO_DEBUG = True" | Add-Content -Path .env
"DATABASE_URL = ""postgresql://username:password@host:port/database""" | Add-Content -Path .env
"PANOPTO_FOLDER_ID = ""your-panopto-folder-id""" | Add-Content -Path .env
```

6. **Run the application**

```powershell
# Run the web application
python app.py

# Or process a transcript directly
python fullpipeline.py https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id=YOUR_VIDEO_ID
```

## Web Interface Usage

The web interface provides a simple way to process Panopto video transcripts:

1. Paste a Panopto video URL in the input field
2. Configure options:
   - Skip timestamp refinement: Faster but less accurate topic mapping
   - HTML Format: Choose between numbered or simple format
   - Language: Select the transcript language
3. Click "Process URL" and wait for processing to complete
4. Download the generated files:
   - Original subtitle file (.srt)
   - Plain text transcript (.txt)
   - Excel spreadsheet (.xlsx)
   - Refined Excel with improved timestamps (.xlsx)
   - Speaker links with summaries (.html)
   - Meeting summaries (.html)
   - Speaker and meeting summaries (.md)

## Command Line Usage

### 1. Full Pipeline (URL to Summaries)

Process a Panopto video URL from start to finish:

```bash
python fullpipeline.py https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id=YOUR_VIDEO_ID [options]
```

Options:
- `--skip-refinement`: Skip the start time refinement step
- `--language LANGUAGE`: Language code (default: "English_USA")
- `--meeting-root DIRECTORY`: Output directory for processed files
- `--skip-timestamps`: Skip file timestamp adjustments
- `--enhanced-summaries`: Use enhanced speaker summaries with multiple topics

### 2. Local File Processing

Process a local VTT or SRT file:

```bash
python pipeline.py input.srt VIDEO_ID [options]
```

Options:
- `--skip-refinement`: Skip the start time refinement step
- `--html-format {simple|numbered}`: Output format for HTML
- `--output-dir DIRECTORY`: Directory to store output files
- `--meeting-name NAME`: Custom name for output files

### 3. Individual Component Usage

Each script can also be used independently:

#### Extract Video ID from URL
```bash
python url2id.py [url]
```

#### Download SRT Transcript
```bash
python url2file.py [url] [output_file] [--language LANGUAGE]
```

#### Convert SRT/VTT to Text
```bash
python vtt2txt.py input.vtt [output.txt]
```

#### Convert Text to Excel
```bash
python txt2xlsx.py input.txt [output.xlsx]
```

#### Refine Timestamps
```bash
python refineStartTimes.py input.xlsx [output.xlsx]
```

#### Convert Excel to HTML with Summaries
```bash
python xlsx2html.py input.xlsx VIDEO_ID [output.html] [--format={simple|numbered}]
```

## Output Files

For a video with ID `meeting_name`, the pipeline produces:

- `meeting_name.srt` - Original subtitle file
- `meeting_name.txt` - Plain text transcript with timestamps
- `meeting_name.xlsx` - Excel formatted transcript with speaker highlighting
- `meeting_name_refined.xlsx` - Excel with improved timestamp matching
- `meeting_name_speaker_summaries.html` - HTML with speaker links and summaries
- `meeting_name_meeting_summaries.html` - HTML with batch summaries and topic links
- `meeting_name_speaker_summaries.md` - Markdown speaker summaries
- `meeting_name_meeting_summaries.md` - Markdown meeting summaries

## Advanced Features

### Enhanced Speaker Summaries

The pipeline can generate detailed speaker-specific summaries with multiple topics per speaker:

- Identifies distinct topics for each speaker using NLP
- Creates separate summaries for each topic with timestamps
- Links directly to the exact point in the video where each topic begins
- Formats summaries in both HTML and Markdown formats

Enable with `--enhanced-summaries` flag or enable in xlsx2html.py.

### Timestamp Refinement

The `refineStartTimes.py` script improves the accuracy of speaker timestamp links:

- Analyzes text content for better topic-to-timestamp matching
- Uses NLP to identify the most relevant speaker instances
- Updates Excel with improved timestamp mappings
- Generates corrected markdown files with accurate timestamps

### Customization

Various parameters can be adjusted:

- In **txt2xlsx.py**: Color generation, column formatting
- In **refineStartTimes.py**:
  - Text similarity thresholds
  - Keyword extraction settings
  - Maximum time gap for matching
- In **xlsx2html.py**: 
  - Batch size for summaries (`DEFAULT_BATCH_SIZE_MINUTES`)
  - AI model selection (via `.env` file)
  - Summary prompt templates
  - HTML and Markdown formatting

## Environment Variables

Create a `.env` file in the project directory to configure:

```
# Django Configuration
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=True

# Database Configuration
DATABASE_URL=postgresql://username:password@host:port/database

# Panopto Configuration
PANOPTO_FOLDER_ID=your-panopto-folder-id

# Celery Configuration (optional)
CELERY_BROKER_URL=redis://localhost:6379/0
```

## Troubleshooting

### Common Issues

- **Missing NLTK Data**: If you get NLTK errors, run the NLTK download commands manually.
- **API Key Issues**: Check that your API_KEY is correctly set in .env or as an environment variable.
- **Memory Errors**: For large transcripts, try increasing Docker container memory allocation.
- **File Permission Issues**: Ensure the temp_files directory is writable.

### Logs

Check the application logs for detailed error information. In Docker:

```bash
docker logs transcript-processor
```

## Project Structure

```
.
├── app.py                    # Flask web application
├── docker-compose.yml        # Docker Compose configuration
├── Dockerfile                # Docker build configuration
├── fullpipeline.py           # Full URL-to-summaries pipeline
├── pipeline.py               # Local file processing pipeline
├── html_bold_converter.py    # Convert markdown bold to HTML
├── refineStartTimes.py       # Timestamp refinement logic
├── requirements.txt          # Python dependencies
├── speaker_summary_utils.py  # Speaker summary generation utilities
├── templates/                # Flask HTML templates
│   └── index.html            # Web interface
├── url2file.py               # URL to SRT downloader
├── url2id.py                 # URL to video ID extractor
├── url2meeting_name.py       # URL to meeting name extractor
├── utils.py                  # Shared utility functions
├── vtt2txt.py                # VTT/SRT to text converter
└── xlsx2html.py              # Excel to HTML/MD converter
```

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for improvements.

## License

This project is available under the MIT License.

## Acknowledgments

This pipeline was developed to help process and analyze video content efficiently, with a focus on academic and research meetings.