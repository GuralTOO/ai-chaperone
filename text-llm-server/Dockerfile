# ============================================================================
# Application Layer - SQS Worker
# ============================================================================
FROM python:3.12-slim

# Set non-interactive frontend
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies for video processing (av library needs ffmpeg)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswscale-dev \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./
COPY src/ ./src/

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Environment variables with defaults
ENV VLLM_URL="http://localhost:8000" \
    AWS_REGION="us-east-2" \
    QUEUE_NAME="ai-chaperone-text-llm-queue" \
    PYTHONUNBUFFERED="1"

# Run the SQS worker
CMD ["aws-server"]