let timerInterval;
let startTime;

const startBtn = document.getElementById('start');
const stopBtn = document.getElementById('stop');
const statusText = document.getElementById('status');
const timerDisplay = document.getElementById('timer');
const visualizer = document.getElementById('visualizer');

function updateTimer() {
    const now = Date.now();
    const diff = now - startTime;
    const h = Math.floor(diff / 3600000).toString().padStart(2, '0');
    const m = Math.floor((diff % 3600000) / 60000).toString().padStart(2, '0');
    const s = Math.floor((diff % 60000) / 1000).toString().padStart(2, '0');
    timerDisplay.textContent = `${h}:${m}:${s}`;
}

function startTimer(existingStartTime) {
    startTime = existingStartTime || Date.now();
    updateTimer(); // Update immediately to show correct time
    timerInterval = setInterval(updateTimer, 1000);
    visualizer.parentElement.classList.add('recording');
}

function stopTimer() {
    clearInterval(timerInterval);
    visualizer.parentElement.classList.remove('recording');
    timerDisplay.textContent = '00:00:00';
}

startBtn.addEventListener('click', async () => {
    statusText.textContent = "Requesting capture...";

    // Get the current tab ID
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    // Request Mic permission in a visible UI first (required by Chrome)
    try {
        statusText.textContent = "Checking microphone access...";
        const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        micStream.getTracks().forEach(t => t.stop()); // Just checking, don't keep it open
    } catch (e) {
        statusText.textContent = "Mic access denied. Please allow it.";
        console.error("Mic permission Error:", e);
        return;
    }

    chrome.runtime.sendMessage({
        action: "START_RECORDING",
        tabId: tab.id
    }, (response) => {
        if (chrome.runtime.lastError) {
            statusText.textContent = "Error: " + chrome.runtime.lastError.message;
            return;
        }

        if (response && response.success) {
            startBtn.classList.add('hidden');
            stopBtn.classList.remove('hidden');
            statusText.textContent = "Recording tab audio...";
            startTimer();
        } else {
            statusText.textContent = "Failed: " + (response ? response.error : "Unknown error");
            console.error("Recording start failed", response);
        }
    });
});

stopBtn.addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: "STOP_RECORDING" }, (response) => {
        startBtn.classList.remove('hidden');
        stopBtn.classList.add('hidden');
        statusText.textContent = "Recording saved!";
        stopTimer();
    });
});

// Check current state on popup open
chrome.runtime.sendMessage({ action: "GET_STATUS" }, (response) => {
    if (response && response.isRecording) {
        startBtn.classList.add('hidden');
        stopBtn.classList.remove('hidden');
        statusText.textContent = "Recording in progress...";

        if (response.startTime) {
            startTimer(response.startTime);
        } else {
            visualizer.parentElement.classList.add('recording');
        }
    }
});
