let recorder;
let chunks = [];

// Signal readiness
chrome.runtime.sendMessage({ action: "OFFSCREEN_READY" });

chrome.runtime.onMessage.addListener(async (message) => {
    if (message.action === "INITIALIZE_RECORDER") {
        startRecording(message.streamId);
    } else if (message.action === "FINALIZE_RECORDER") {
        stopRecording();
    }
});

async function startRecording(tabStreamId) {
    console.log("Starting Dual-Channel Recording (Tab + Mic)...");
    try {
        // 1. Capture Tab Audio
        const tabStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                mandatory: {
                    chromeMediaSource: 'tab',
                    chromeMediaSourceId: tabStreamId
                }
            },
            video: false
        });

        // 2. Capture Microphone Audio
        const micStream = await navigator.mediaDevices.getUserMedia({
            audio: true,
            video: false
        });

        // 3. Mix them together using Web Audio API
        const audioContext = new AudioContext();
        const tabSource = audioContext.createMediaStreamSource(tabStream);
        const micSource = audioContext.createMediaStreamSource(micStream);
        const destination = audioContext.createMediaStreamDestination();

        tabSource.connect(destination);
        micSource.connect(destination);

        // Also loop back the tab audio so you can hear it
        tabSource.connect(audioContext.destination);

        // 4. Record the mixed destination
        recorder = new MediaRecorder(destination.stream, { mimeType: 'audio/webm' });
        chunks = [];

        recorder.ondataavailable = (e) => {
            if (e.data.size > 0) {
                chunks.push(e.data);
                console.log(`Chunk captured: ${e.data.size} bytes.`);
            }
        };

        recorder.onstop = async () => {
            console.log("Dual recording stopped. Processing...");
            const blob = new Blob(chunks, { type: 'audio/webm' });

            const reader = new FileReader();
            reader.onloadend = () => {
                chrome.runtime.sendMessage({
                    action: "DOWNLOAD_CAPTURE",
                    dataUrl: reader.result
                });
            };
            reader.readAsDataURL(blob);

            // Cleanup all tracks
            tabStream.getTracks().forEach(t => t.stop());
            micStream.getTracks().forEach(t => t.stop());
            audioContext.close();
            chunks = [];
        };

        recorder.start(2000);
        console.log("Dual-Channel Recording is ACTIVE");
    } catch (err) {
        console.error("Critical error in dual-stream start:", err);
    }
}

function stopRecording() {
    if (recorder && recorder.state !== "inactive") {
        recorder.stop();
    }
}
