# Use an official Python runtime as a parent image
# python:3.13-slim is used because the project seems to be using Python 3.13
# based on the __pycache__ filenames.
FROM python:3.13-slim

# Set environment variables
# PYTHONUNBUFFERED=1 ensures that logs are sent straight to stdout/stderr (essential for AWS ECS/CloudWatch)
# PYTHONDONTWRITEBYTECODE=1 prevents Python from writing .pyc files to disc
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Set work directory
WORKDIR /app

# Install system dependencies
# libpq-dev is often needed for psycopg2/psycopg, though psycopg[binary] is in requirements.txt
# we include it for safety and build-time stability.
# curl is added for the healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
# .dockerignore should handle excluding unnecessary files
COPY src/ /app/src/

# Create a non-root user and switch to it for security
# AWS ECS best practice is to avoid running as root.
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Expose the port the app runs on
EXPOSE 8000

# Healthcheck for ECS to monitor container health
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Command to run the application
# We use uvicorn to run the FastAPI app. 
# host 0.0.0.0 is required to be accessible from outside the container.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
