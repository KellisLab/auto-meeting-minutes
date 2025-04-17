FROM python:3.12.7-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download NLTK data required for NLP processing in refineStartTimes.py
RUN python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab'); nltk.download('stopwords')"

# Copy application code
COPY . .

# Create necessary directories for app operation
RUN mkdir -p temp_files templates static/css

# Make Python scripts executable
RUN chmod +x *.py

# Move template file to correct location if needed
RUN if [ -f index.html ] && [ ! -f templates/index.html ]; then \
    mv index.html templates/; \
    fi

# Expose port for the Flask application
EXPOSE 5001

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1
# Configure the model to use for summarization - override in docker-compose.yml if needed
ENV GPT_MODEL="chatgpt-4o-latest"

# Run the application
CMD ["python", "app.py"]