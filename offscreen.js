let recorder;
const DB_NAME = "MemoChanRecordingDB";
const STORE_NAME = "chunks";
let db;

// 1. Initialize IndexedDB
async function initDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, 1);
        request.onupgradeneeded = (e) => {
            const database = e.target.result;
            if (!database.objectStoreNames.contains(STORE_NAME)) {
                database.createObjectStore(STORE_NAME, { autoIncrement: true });
            }
        };
        request.onsuccess = (e) => {
            db = e.target.result;
            resolve(db);
        };
        request.onerror = (e) => reject(e.target.error);
    });
}

async function addChunkToDB(chunk) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction([STORE_NAME], "readwrite");
        const store = transaction.objectStore(STORE_NAME);
        const request = store.add(chunk);
        request.onsuccess = () => resolve();
        request.onerror = (e) => reject(e.target.error);
    });
}

async function getAllChunksFromDB() {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction([STORE_NAME], "readonly");
        const store = transaction.objectStore(STORE_NAME);
        const request = store.getAll();
        request.onsuccess = (e) => resolve(e.target.result);
        request.onerror = (e) => reject(e.target.error);
    });
}

async function clearDB() {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction([STORE_NAME], "readwrite");
        const store = transaction.objectStore(STORE_NAME);
        const request = store.clear();
        request.onsuccess = () => resolve();
        request.onerror = (e) => reject(e.target.error);
    });
}

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
        await initDB();
        await clearDB(); // Ensure fresh start

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
        // Use a supported mimeType, fallback to default
        const options = { mimeType: 'audio/webm;codecs=opus' };
        if (!MediaRecorder.isTypeSupported(options.mimeType)) {
            console.warn("MimeType not supported, falling back");
            delete options.mimeType;
        }

        recorder = new MediaRecorder(destination.stream, options);

        recorder.ondataavailable = async (e) => {
            if (e.data.size > 0) {
                // Store chunk in IndexedDB instead of RAM array
                await addChunkToDB(e.data);
                console.log(`Chunk stored: ${e.data.size} bytes.`);
            }
        };

        recorder.onerror = (err) => {
            console.error("MediaRecorder Error:", err);
        };

        recorder.onstop = async () => {
            console.log("Dual recording stopped. Assembling chunks from IndexedDB...");

            try {
                const chunks = await getAllChunksFromDB();
                const blob = new Blob(chunks, { type: 'audio/webm' });
                const url = URL.createObjectURL(blob);

                const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
                const filename = `meeting-recording-${timestamp}.webm`;

                console.log("Offscreen created Blob URL:", url, `(Size: ${(blob.size / 1024 / 1024).toFixed(2)} MB)`);

                // Send the URL string to background script. 
                // String is small, avoids the 64MB limit.
                chrome.runtime.sendMessage({
                    action: "DOWNLOAD_BLOB_URL",
                    url: url,
                    filename: filename
                });

                // Note: We don't revoke here because the background script needs the URL to be valid
                // We'll trust the browser to clean up when the offscreen document closes
                // or we can add a listener to revoke later.
            } catch (err) {
                console.error("Error assembling recording:", err);
            }

            // Cleanup tracks
            tabStream.getTracks().forEach(t => t.stop());
            micStream.getTracks().forEach(t => t.stop());
            audioContext.close();
        };

        recorder.start(5000); // 5 second chunks for stability
        console.log("Dual-Channel Recording is ACTIVE");

        // Keep-alive heartbeat (optional but good for long sessions)
        const keepAlive = setInterval(() => {
            if (recorder && recorder.state === "recording") {
                chrome.runtime.sendMessage({ action: "HEARTBEAT" });
            } else {
                clearInterval(keepAlive);
            }
        }, 10000);

    } catch (err) {
        console.error("Critical error in dual-stream start:", err);
        chrome.runtime.sendMessage({ action: "RECORDING_FAILED", error: err.message });
    }
}

function stopRecording() {
    if (recorder && recorder.state !== "inactive") {
        recorder.stop();
    }
}

