let isRecording = false;
let pendingStreamId = null;

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    // 1. Offscreen Readiness
    if (request.action === "OFFSCREEN_READY") {
        if (pendingStreamId) {
            chrome.runtime.sendMessage({
                action: "INITIALIZE_RECORDER",
                streamId: pendingStreamId
            });
            pendingStreamId = null;
        }
    }

    // 2. Download Request from Offscreen
    if (request.action === "DOWNLOAD_CAPTURE") {
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const filename = `meeting-recording-${timestamp}.webm`;

        console.log("Service Worker triggering download:", filename);
        chrome.downloads.download({
            url: request.dataUrl,
            filename: filename,
            saveAs: false
        });

        // Close offscreen after download is initiated
        setTimeout(() => {
            chrome.offscreen.closeDocument();
            chrome.storage.local.remove(['recordingState']);
        }, 2000);
    }

    // 3. Popup Commands
    if (request.action === "START_RECORDING") {
        startRecording(request.tabId).then(() => {
            // Save start time and state
            chrome.storage.local.set({
                recordingState: {
                    startTime: Date.now(),
                    isRecording: true
                }
            });
            sendResponse({ success: true });
        }).catch(err => {
            sendResponse({ success: false, error: err.message });
        });
        return true;
    }

    if (request.action === "STOP_RECORDING") {
        chrome.runtime.sendMessage({ action: "FINALIZE_RECORDER" });
        chrome.storage.local.set({
            recordingState: {
                isRecording: false
            }
        });
        sendResponse({ success: true });
        return true;
    }

    if (request.action === "GET_STATUS") {
        // Check both storage and actual offscreen existence for truth
        Promise.all([
            chrome.storage.local.get(['recordingState']),
            chrome.runtime.getContexts({ contextTypes: ['OFFSCREEN_DOCUMENT'] })
        ]).then(([data, contexts]) => {
            const hasOffscreen = contexts.length > 0;
            const state = data.recordingState || {};

            // If storage says recording but no offscreen, it's a stale state -> not recording
            // If offscreen exists but storage says nothing, we assume recording (recoveyr)
            const isRecording = hasOffscreen && (state.isRecording !== false);

            sendResponse({
                isRecording: isRecording,
                startTime: isRecording ? state.startTime : null
            });
        });
        return true; // Async response
    }
});

async function startRecording(tabId) {
    const existingContexts = await chrome.runtime.getContexts({
        contextTypes: ['OFFSCREEN_DOCUMENT']
    });

    if (existingContexts.length > 0) {
        await chrome.offscreen.closeDocument();
    }

    pendingStreamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tabId });

    await chrome.offscreen.createDocument({
        url: 'offscreen.html',
        reasons: ['USER_MEDIA'],
        justification: 'Recording tab audio'
    });
}
