import os
import time
import sys
import torch
import torchaudio
import subprocess
import imageio_ffmpeg

from datetime import datetime
from dotenv import load_dotenv

try:
    from faster_whisper import WhisperModel
    import ctranslate2
except ImportError:
    print("Error: faster_whisper not found. Install it with: pip install faster-whisper")
    sys.exit(1)

try:
    from pyannote.audio import Pipeline
except ImportError:
    print("Warning: pyannote.audio not found. Speaker identification will be disabled.")
    Pipeline = None

# Load environment variables
load_dotenv()
HF_TOKEN = os.getenv("HF_TOKEN")

# Configuration
WATCH_DIR = os.path.join(os.path.expanduser("~"), "Downloads")
PROCESSED_DIR = "processed_recordings"
# GTX 1660 Ti has 6GB VRAM. large-v3 in int8_float16 takes ~3.5GB.
MODEL_SIZE = "medium" 
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "int8_float16" if DEVICE == "cuda" else "int8"

if not os.path.exists(PROCESSED_DIR):
    os.makedirs(PROCESSED_DIR)

print(f"🚀 MemoChan Advanced Backend Started!")
print(f"📁 Watching: {WATCH_DIR}")
print(f"⚙️  Device: {DEVICE.upper()} (Compute: {COMPUTE_TYPE})")
print(f"🧠 Loading Whisper model ({MODEL_SIZE})...")

# Initialize models
print("🧠 Initializing Whisper Model...")
try:
    model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    print("✅ Whisper model loaded successfully.")
except Exception as e:
    print(f"❌ Failed to load Whisper model: {e}")
    sys.exit(1)

# Initialize Diarization
diarization_pipeline = None
if Pipeline and HF_TOKEN:
    print("🎙️ Initializing Speaker Diarization pipeline...")
    try:
        diarization_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=HF_TOKEN
        )
        print("⏳ Moving Diarization pipeline to GPU...")
        diarization_pipeline.to(torch.device(DEVICE))
        
        # Suppress reproducibility warning
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        
        print("✅ Diarization ready.")
    except Exception as e:
        print(f"⚠️  Diarization failed to load (check your HF_TOKEN): {e}")
elif Pipeline and not HF_TOKEN:
    print("💡 Tip: Set HF_TOKEN in .env to enable Speaker Identification.")

def convert_to_wav(input_path):
    output_path = input_path.rsplit(".", 1)[0] + ".wav"
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    
    print(f"🔄 Converting to WAV for compatibility...")
    try:
        # Use imageio's ffmpeg binary to convert
        subprocess.run([
            ffmpeg_exe, 
            "-y", # Overwrite if exists
            "-i", input_path, 
            "-ar", "16000", # Convert to 16kHz for ML models
            "-ac", "1", # Mono
            output_path
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path
    except Exception as e:
        print(f"⚠️ Conversion failed: {e}")
        return None

def transcribe_and_diarize(file_path):
    print(f"\n🎧 New recording: {os.path.basename(file_path)}")
    start_time = time.time()
    
    # Pre-process: Convert WEBM -> WAV using ffmpeg binary
    # This fixes issues with torchaudio/pyannote on Windows not liking Opus/WebM
    wav_path = convert_to_wav(file_path)
    processing_path = wav_path if wav_path else file_path
    
    try:
        # 1. Transcribe with word-level timestamps
        print("⏳ Transcribing...")
        segments, info = model.transcribe(processing_path, beam_size=5, word_timestamps=True)
        
        transcript_segments = list(segments)
        
        # 2. Run Diarization if available
        speaker_map = []
        if diarization_pipeline:
            print("⏳ Identifying speakers...")
            # Load audio manually to bypass pyannote internal IO issues
            try:
                waveform, sample_rate = torchaudio.load(processing_path)
                diarization = diarization_pipeline({"waveform": waveform, "sample_rate": sample_rate})
                
                # Support pyannote.audio 4.x+ where output is nested in DiarizeOutput
                annotation = diarization
                if hasattr(diarization, "speaker_diarization"):
                    annotation = diarization.speaker_diarization
                
                for turn, _, speaker in annotation.itertracks(yield_label=True):
                    speaker_map.append({
                        "start": turn.start,
                        "end": turn.end,
                        "speaker": speaker
                    })
            except Exception as e:
                 print(f"⚠️ Diarization failed: {e}")

        # 3. Combine results
        formatted_output = ""
        for segment in transcript_segments:
            # Find dominant speaker for this segment duration
            current_speaker = "Unknown"
            if speaker_map:
                # Basic overlap check: which speaker was active during the middle of this segment
                mid_point = (segment.start + segment.end) / 2
                for entry in speaker_map:
                    if entry["start"] <= mid_point <= entry["end"]:
                        current_speaker = entry["speaker"]
                        break
            
            timestamp = f"[{segment.start:.2f}s -> {segment.end:.2f}s]"
            line = f"{timestamp} [{current_speaker}]: {segment.text.strip()}"
            print(line)
            formatted_output += line + "\n"

        # Save transcript
        base_name = os.path.basename(file_path)
        transcript_path = os.path.join(PROCESSED_DIR, f"{base_name}.txt")
        
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(f"--- MemoChan Advanced Transcript ---\n")
            f.write(f"Date: {datetime.now()}\n")
            f.write(f"Model: {MODEL_SIZE} on {DEVICE.upper()}\n")
            f.write(f"Diarization: {'Enabled' if speaker_map else 'Disabled'}\n")
            f.write("-" * 40 + "\n\n")
            f.write(formatted_output)

        duration = time.time() - start_time
        print(f"✅ Completed in {duration:.1f}s. Saved to: {transcript_path}")
        
        # Cleanup temporary WAV if we made one
        if wav_path and wav_path != file_path and os.path.exists(wav_path):
             os.remove(wav_path)
        
    except Exception as e:
        print(f"❌ Processing failed: {e}")

def main():
    seen_files = set(os.listdir(WATCH_DIR))
    print("\n✅ Backend is in watch mode. Drop a recording to start.")
    try:
        while True:
            current_files = set(os.listdir(WATCH_DIR))
            new_files = current_files - seen_files
            
            for f in new_files:
                if f.startswith("meeting-recording-") and f.endswith(".webm"):
                    full_path = os.path.join(WATCH_DIR, f)
                    time.sleep(2) # Finish download
                    transcribe_and_diarize(full_path)
            
            seen_files = current_files
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n👋 MemoChan stopped.")

if __name__ == "__main__":
    main()
