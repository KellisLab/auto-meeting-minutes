FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download NLTK data
RUN python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p temp_files templates static/css

# Move template file to correct location
RUN if [ -f index.html ] && [ ! -f templates/index.html ]; then \
    mv index.html templates/; \
    fi

# Expose port
EXPOSE 5001

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python", "app.py"]