FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.12, required packages, and create symlink
RUN apt-get update && \
    apt-get install -y software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y \
        python3.12 \
        python3.12-venv \
        python3.12-dev \
        python3-pip \
	curl \
        wget \
        build-essential && \
    ln -sf /usr/bin/python3.12 /usr/bin/python && \
    ln -sf /usr/bin/python3.12 /usr/bin/python3 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python3.12 --version || (echo "Error: python3.12 not found" && exit 1)

RUN python3.12 -m venv venv

RUN ./venv/bin/pip install uv==0.8.17

RUN sh -c ". venv/bin/activate && uv pip install vllm --torch-backend=auto"

ENV MODEL_NAME="/models/gemma-3"
ENV HOST="0.0.0.0"
ENV PORT="8000"
ENV PATH="/app/venv/bin:$PATH" 
EXPOSE 8000
CMD ["vllm", "serve", "/models/gemma-3", "--host", "0.0.0.0", "--port", "8000"]
