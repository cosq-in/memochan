# 🎙️ MemoChan: Your Personal Meeting Scribe

MemoChan is a premium Chrome extension designed to capture meeting audio directly from your browser tab and automatically transcribe it using a local, high-performance Whisper backend.

## ✨ Features
- **Tab Capture**: Records high-quality audio directly from Google Meet, Zoom (Web), or any other tab.
- **Glassmorphic UI**: A stunning, modern interface inspired by high-end productivity tools.
- **Local Transcription**: Uses `faster-whisper` on your own machine. No cloud costs, 100% private.
- **Automatic Workflow**: Just stop the recording, and the backend handles the rest.

---

## 🚀 Getting Started

### 1. Install Extension
1. Open Chrome and go to `chrome://extensions`.
2. Enable **Developer Mode** (toggle in the top right).
3. Click **Load unpacked** and select the `memochan` folder.

### 2. Setup Python Backend
Make sure you have Python installed. Then, set up the dependencies:

```bash
# Recommended: Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Run the Scribe
Start the backend script to watch for new recordings:

```bash
python notes.py
```

---

## 🛠️ Usage
1. Open your meeting (Google Meet, Zoom, etc.).
2. Click the **MemoChan** icon in your extension bar.
3. Click **Start Recording**.
4. When finished, click **Stop & Save**.
5. The recording will download to your `Downloads` folder.
6. The Python backend will detect the file, transcribe it, and save the result in the `processed_recordings` folder.

---

## 📂 Project Structure
- `manifest.json`: Extension configuration.
- `popup.html/.css/.js`: The beautiful user interface.
- `background.js`: Manages the recording process.
- `offscreen.html/.js`: Specialized hidden document for tab audio capture.
- `notes.py`: The Whisper transcription engine.

---

## 🔥 Pro Tips
- **Model Size**: In `notes.py`, you can change `MODEL_SIZE` from `base` to `medium` or `large-v3` for significantly better accuracy if your hardware allows.
- **Privacy**: Since all transcription happens locally, your meeting data never leaves your computer.

---

*Built with ❤️ for hackers who value privacy and aesthetics.*
