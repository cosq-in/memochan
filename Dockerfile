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
    requests

# Copy worker script
COPY worker.py .

# Command to run the worker
CMD [ "python", "-u", "/app/worker.py" ]
