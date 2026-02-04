# Use PyTorch with CUDA as base
FROM pytorch/pytorch:2.2.1-cuda12.1-cudnn8-devel

# Set working directory
WORKDIR /app

# Install system dependencies (including ffmpeg)
RUN apt-get update && apt-get install -y ffmpeg git && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# We install higher level packages first to ensure compatibility
RUN pip install --no-cache-dir \
    runpod \
    faster-whisper \
    pyannote.audio \
    imageio-ffmpeg \
    requests \
    transformers \
    accelerate \
    bitsandbytes

# Pre-download models (Whisper + Phi-3) to speed up container start
RUN python3 -c "from faster_whisper import WhisperModel; WhisperModel('large-v3', device='cpu')"
RUN python3 -c "from transformers import AutoModelForCausalLM, AutoTokenizer; \
    AutoTokenizer.from_pretrained('microsoft/Phi-3-mini-4k-instruct'); \
    AutoModelForCausalLM.from_pretrained('microsoft/Phi-3-mini-4k-instruct', torch_dtype='auto', trust_remote_code=True)"

# Copy worker script
COPY worker.py .

# Command to run the worker
CMD [ "python", "-u", "/app/worker.py" ]
