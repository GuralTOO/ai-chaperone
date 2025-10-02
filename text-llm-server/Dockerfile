# ============================================================================
# Application Layer - SQS Worker
# ============================================================================
FROM python:3.12-slim

# Set non-interactive frontend
ENV DEBIAN_FRONTEND=noninteractive

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