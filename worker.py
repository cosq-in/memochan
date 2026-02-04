import os
import torch
import torchaudio
import subprocess
import imageio_ffmpeg
import runpod
import requests
import uuid
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline

# 1. Global Initialization (Keeps models in VRAM across requests)
HF_TOKEN = os.getenv("HF_TOKEN")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "float16" if DEVICE == "cuda" else "int8"
# On RunPod we can usually handle large-v3
MODEL_SIZE = os.getenv("MODEL_SIZE", "large-v3")

print(f"🚀 Initializing MemoChan Worker (Device: {DEVICE})")

# Load Whisper
model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)

# Load Diarization
diarization_pipeline = None
if HF_TOKEN:
    try:
        diarization_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=HF_TOKEN
        )
        diarization_pipeline.to(torch.device(DEVICE))
        # Suppress reproducibility warning
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
    except Exception as e:
        print(f"⚠️ Diarization load failed: {e}")

def convert_to_wav(input_path):
    output_path = input_path.rsplit(".", 1)[0] + "_converted.wav"
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    try:
        subprocess.run([
            ffmpeg_exe, "-y", "-i", input_path,
            "-ar", "16000", "-ac", "1", output_path
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path
    except Exception as e:
        print(f"⚠️ Conversion error: {e}")
        return None

def handler(event):
    """
    RunPod Handler
    Input event format: { "input": { "audio_url": "..." } }
    """
    job_input = event.get("input", {})
    audio_url = job_input.get("audio_url")
    
    if not audio_url:
        return {"error": "No audio_url provided"}

    # 1. Download File
    job_id = str(uuid.uuid4())
    input_filename = f"input_{job_id}.webm"
    
    try:
        response = requests.get(audio_url)
        with open(input_filename, "wb") as f:
            f.write(response.content)
    except Exception as e:
        return {"error": f"Download failed: {str(e)}"}

    # 2. Pre-process (WEBM -> WAV)
    processing_path = convert_to_wav(input_filename)
    if not processing_path:
        processing_path = input_filename

    try:
        # 3. Transcribe
        segments, info = model.transcribe(processing_path, beam_size=5, word_timestamps=True)
        transcript_segments = list(segments)

        # 4. Diarize
        speaker_map = []
        if diarization_pipeline:
            waveform, sample_rate = torchaudio.load(processing_path)
            diar_output = diarization_pipeline({"waveform": waveform, "sample_rate": sample_rate})
            
            annotation = diar_output
            if hasattr(diar_output, "speaker_diarization"):
                annotation = diar_output.speaker_diarization
                
            for turn, _, speaker in annotation.itertracks(yield_label=True):
                speaker_map.append({
                    "start": turn.start,
                    "end": turn.end,
                    "speaker": speaker
                })

        # 5. Format JSON Response
        final_results = []
        for segment in transcript_segments:
            current_speaker = "Unknown"
            if speaker_map:
                mid_point = (segment.start + segment.end) / 2
                for entry in speaker_map:
                    if entry["start"] <= mid_point <= entry["end"]:
                        current_speaker = entry["speaker"]
                        break
            
            final_results.append({
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "speaker": current_speaker,
                "text": segment.text.strip()
            })

        # Cleanup
        if os.path.exists(input_filename): os.remove(input_filename)
        if processing_path and os.path.exists(processing_path) and processing_path != input_filename:
            os.remove(processing_path)

        return {
            "job_id": job_id,
            "segments": final_results,
            "language": info.language,
            "language_probability": info.language_probability
        }

    except Exception as e:
        return {"error": f"Processing failed: {str(e)}"}

# Start RunPod Serverless
runpod.serverless.start({"handler": handler})
