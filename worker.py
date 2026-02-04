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
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

# 1. Global Initialization (Keeps models in VRAM across requests)
HF_TOKEN = os.getenv("HF_TOKEN")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "float16" if DEVICE == "cuda" else "int8"
MODEL_SIZE = os.getenv("MODEL_SIZE", "large-v3")
LLM_MODEL = "microsoft/Phi-3-mini-4k-instruct"

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
    except Exception as e:
        print(f"⚠️ Diarization load failed: {e}")

# Load LLM for Summarization (Using Phi-3 Mini)
print(f"🧠 Loading Summarizer: {LLM_MODEL}")
try:
    llm_tokenizer = AutoTokenizer.from_pretrained(LLM_MODEL)
    llm_model = AutoModelForCausalLM.from_pretrained(
        LLM_MODEL, 
        device_map="auto", 
        torch_dtype="auto", 
        trust_remote_code=True
    )
    summarizer = pipeline(
        "text-generation", 
        model=llm_model, 
        tokenizer=llm_tokenizer, 
    )
except Exception as e:
    print(f"⚠️ LLM load failed: {e}")
    summarizer = None

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

def generate_summary(transcript_text):
    if not summarizer:
        return "Summarization model not loaded."
    
    prompt = f"<|user|>\nYou are a professional meeting assistant. Based on the following transcript, provide a concise summary, key takeaways, and a list of action items.\n\nTRANSCRIPT:\n{transcript_text}\n<|assistant|>\n"
    
    try:
        outputs = summarizer(
            prompt, 
            max_new_tokens=500, 
            do_sample=True, 
            temperature=0.7,
            return_full_text=False
        )
        return outputs[0]['generated_text'].strip()
    except Exception as e:
        return f"Summary generation failed: {str(e)}"

def handler(event):
    job_input = event.get("input", {})
    audio_url = job_input.get("audio_url")
    
    if not audio_url:
        return {"error": "No audio_url provided"}

    job_id = str(uuid.uuid4())
    input_filename = f"input_{job_id}.webm"
    
    try:
        response = requests.get(audio_url)
        with open(input_filename, "wb") as f:
            f.write(response.content)
    except Exception as e:
        return {"error": f"Download failed: {str(e)}"}

    processing_path = convert_to_wav(input_filename)
    if not processing_path:
        processing_path = input_filename

    try:
        # 1. Transcribe
        segments, info = model.transcribe(processing_path, beam_size=5, word_timestamps=True)
        transcript_segments = list(segments)

        # 2. Diarize
        speaker_map = []
        if diarization_pipeline:
            waveform, sample_rate = torchaudio.load(processing_path)
            diar_output = diarization_pipeline({"waveform": waveform, "sample_rate": sample_rate})
            annotation = diar_output.speaker_diarization if hasattr(diar_output, "speaker_diarization") else diar_output
            
            for turn, _, speaker in annotation.itertracks(yield_label=True):
                speaker_map.append({"start": turn.start, "end": turn.end, "speaker": speaker})

        # 3. Format Segments and build full transcript for LLM
        final_results = []
        full_transcript_raw = ""
        for segment in transcript_segments:
            current_speaker = "Unknown"
            if speaker_map:
                mid_point = (segment.start + segment.end) / 2
                for entry in speaker_map:
                    if entry["start"] <= mid_point <= entry["end"]:
                        current_speaker = entry["speaker"]
                        break
            
            text = segment.text.strip()
            final_results.append({
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "speaker": current_speaker,
                "text": text
            })
            full_transcript_raw += f"{current_speaker}: {text}\n"

        # 4. Generate AI Summary
        meeting_summary = generate_summary(full_transcript_raw)

        # Cleanup
        if os.path.exists(input_filename): os.remove(input_filename)
        if processing_path and os.path.exists(processing_path) and processing_path != input_filename:
            os.remove(processing_path)

        return {
            "job_id": job_id,
            "summary": meeting_summary,
            "segments": final_results,
            "language": info.language
        }

    except Exception as e:
        return {"error": f"Processing failed: {str(e)}"}

runpod.serverless.start({"handler": handler})
