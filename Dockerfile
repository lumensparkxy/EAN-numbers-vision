FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libzbar0 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install poetry
RUN pip install poetry==1.7.1

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Configure poetry and install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root --only main

# Copy application code
COPY src/ ./src/
COPY workers/ ./workers/
COPY tools/ ./tools/

# Install the application
RUN poetry install --no-interaction --no-ansi --only main

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default command (can be overridden)
CMD ["python", "-m", "workers.dispatcher.main"]
