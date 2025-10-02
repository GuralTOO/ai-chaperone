#!/bin/bash
set -e

# ============================================================================
# Configuration with defaults
# ============================================================================
MODEL_ID="${MODEL_ID:-google/gemma-3-4b-it}"
MODEL_DIR="${MODEL_DIR:-/models}"
HF_TOKEN="${HF_TOKEN:-}"
HF_HUB_CACHE="${HF_HUB_CACHE:-/home/vllm/.cache/huggingface}"

# VLLM Configuration
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.94}"
TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE:-1}"
VLLM_ARGS="${VLLM_ARGS:-}"

# ============================================================================
# Helper Functions
# ============================================================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >&2
}

check_model_exists() {
    local model_path="$1"
    if [ -f "${model_path}/config.json" ]; then
        return 0
    fi
    return 1
}

check_write_permissions() {
    local dir="$1"
    # Check if directory exists and is writable
    if [ ! -d "${dir}" ]; then
        log "ERROR: Directory ${dir} does not exist"
        return 1
    fi
    
    if [ ! -w "${dir}" ]; then
        log "ERROR: No write permissions to ${dir}"
        log "The container runs as UID $(id -u) (user: $(whoami))"
        log ""
        log "To fix this, run one of these commands on the host:"
        log "  Option 1: sudo chown -R 1001:1001 ${dir}"
        log "  Option 2: Run container with --user \$(id -u):\$(id -g)"
        log "  Option 3: Use a Docker volume instead of bind mount"
        log ""
        return 1
    fi
    return 0
}

download_from_huggingface() {
    log "Downloading model '${MODEL_ID}' from HuggingFace..."
    
    if [ -n "${HF_TOKEN}" ]; then
        log "Using HuggingFace token: ${HF_TOKEN}"
        export HUGGING_FACE_HUB_TOKEN="${HF_TOKEN}"
    else
        log "No HuggingFace token provided"
    fi
    
    # Set cache directory if specified
    if [ -n "${HF_HUB_CACHE}" ]; then
        export HF_HOME="${HF_HUB_CACHE}"
    fi
    
    local model_path="${MODEL_DIR}/${MODEL_ID//\//_}"
    
    # Try to create the directory
    if ! mkdir -p "${model_path}" 2>/dev/null; then
        log "ERROR: Cannot create directory ${model_path}"
        check_write_permissions "${MODEL_DIR}"
        exit 1
    fi
    
    if ! hf download "${MODEL_ID}" \
        --local-dir "${model_path}" \
        --local-dir-use-symlinks False \
        ${HF_TOKEN:+--token "${HF_TOKEN}"} >&2; then
        log "ERROR: Failed to download model from HuggingFace"
        exit 1
    fi
    
    log "Model downloaded successfully to ${model_path}"
    
    # Only output to stdout - this is what gets captured
    echo "${model_path}"
}

# ============================================================================
# Main Logic
# ============================================================================

log "Starting VLLM container initialization..."
log "Running as user: $(whoami) (UID: $(id -u), GID: $(id -g))"
log "Model ID: ${MODEL_ID}"
log "Model Directory: ${MODEL_DIR}"

# Check write permissions early
if ! check_write_permissions "${MODEL_DIR}"; then
    exit 1
fi

if [[ "${MODEL_ID}" == /* ]]; then
    MODEL_PATH="${MODEL_ID}"
    log "Using absolute model path: ${MODEL_PATH}"
else
    MODEL_PATH="${MODEL_DIR}/${MODEL_ID//\//_}"
    
    if check_model_exists "${MODEL_PATH}"; then
        log "Model found at ${MODEL_PATH}, skipping download"
    else
        log "Model not found locally, downloading..."
        MODEL_PATH=$(download_from_huggingface)
    fi
fi

if ! check_model_exists "${MODEL_PATH}"; then
    log "ERROR: Model not found at ${MODEL_PATH}"
    exit 1
fi

log "Starting VLLM server..."
log "Command: python3 -m vllm.entrypoints.openai.api_server --model ${MODEL_PATH} ..."

# Build command properly using array to handle spaces/special chars
exec python3 -m vllm.entrypoints.openai.api_server \
    --model "${MODEL_PATH}" \
    --host "${HOST}" \
    --port "${PORT}" \
    --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
    --tensor-parallel-size "${TENSOR_PARALLEL_SIZE}" \
    ${MAX_MODEL_LEN:+--max-model-len "${MAX_MODEL_LEN}"} \
    ${VLLM_ARGS}