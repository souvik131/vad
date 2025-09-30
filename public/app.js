class AudioStreamingApp {
    constructor() {
        this.ws = null;
        this.audioContext = null;
        this.mediaStream = null;
        this.analyser = null;
        this.audioInput = null;
        this.isRecording = false;
        this.frameCount = 0;
        this.connectButton = document.getElementById('connectButton');
        this.startRecordingButton = document.getElementById('startRecordingButton');
        this.stopRecordingButton = document.getElementById('stopRecordingButton');
        this.statusElement = document.getElementById('status');
        this.vadStatusElement = document.getElementById('vadStatus');
        // Create VAD details element
        this.vadDetailsElement = document.createElement('div');
        this.vadDetailsElement.id = 'vadDetails';
        this.vadDetailsElement.style.cssText = `
            margin-top: 20px;
            padding: 15px;
            border: 1px solid #ddd;
            border-radius: 8px;
            background-color: #f9f9f9;
            font-family: monospace;
            font-size: 12px;
            line-height: 1.4;
        `;
        document.body.appendChild(this.vadDetailsElement);
        this.setupEventListeners();
    }
    setupEventListeners() {
        this.connectButton.addEventListener('click', () => this.connect());
        this.startRecordingButton.addEventListener('click', () => this.startRecording());
        this.stopRecordingButton.addEventListener('click', () => this.stopRecording());
    }
    async connect() {
        try {
            this.ws = new WebSocket('ws://127.0.0.1:3001');
            this.ws.onopen = () => {
                this.updateStatus('Connected to Python VAD Server', 'connected');
                this.connectButton.disabled = true;
                this.startRecordingButton.disabled = false;
                console.log('Connected to WebSocket server');
            };
            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.is_speech !== undefined) {
                        this.handleVADResult(data);
                    }
                }
                catch (error) {
                    console.error('Error parsing WebSocket message:', error);
                }
            };
            this.ws.onclose = () => {
                this.updateStatus('Disconnected', 'disconnected');
                this.connectButton.disabled = false;
                this.startRecordingButton.disabled = true;
                this.stopRecordingButton.disabled = true;
                console.log('WebSocket connection closed');
            };
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.updateStatus('Connection Error', 'error');
            };
        }
        catch (error) {
            console.error('Connection error:', error);
            this.updateStatus('Connection Failed', 'error');
        }
    }
    handleVADResult(result) {
        // Update VAD status with visual indicators
        if (result.is_speech) {
            this.vadStatusElement.innerHTML = `
                <span style="color: #28a745; font-weight: bold;">
                    🎤 SPEECH DETECTED
                </span>
            `;
            this.vadStatusElement.style.backgroundColor = '#d4edda';
            this.vadStatusElement.style.padding = '8px 12px';
            this.vadStatusElement.style.borderRadius = '4px';
            this.vadStatusElement.style.border = '1px solid #c3e6cb';
        }
        else {
            this.vadStatusElement.innerHTML = `
                <span style="color: #6c757d; font-weight: bold;">
                    🔇 SILENCE
                </span>
            `;
            this.vadStatusElement.style.backgroundColor = '#f8f9fa';
            this.vadStatusElement.style.padding = '8px 12px';
            this.vadStatusElement.style.borderRadius = '4px';
            this.vadStatusElement.style.border = '1px solid #dee2e6';
        }
        // Update detailed VAD information
        this.vadDetailsElement.innerHTML = `
            <h3 style="margin-top: 0; color: #333;">Real-time VAD Analysis</h3>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                <div>
                    <strong>Confidence:</strong> ${(result.confidence * 100).toFixed(1)}%<br>
                    <strong>Speech Votes:</strong> ${result.speech_votes}/3<br>
                    <strong>Frame Count:</strong> ${result.frame_count}<br>
                    <strong>Timestamp:</strong> ${new Date(result.timestamp).toLocaleTimeString()}
                </div>
                <div>
                    <strong>RMS Energy:</strong> ${result.rms_energy.toFixed(6)}<br>
                    <strong>ZCR:</strong> ${result.zcr.toFixed(3)}<br>
                    <strong>Spectral Flatness:</strong> ${result.spectral_flatness.toFixed(3)}<br>
                    <strong>Status:</strong> ${result.is_speech ? '🎤 SPEECH' : '🔇 SILENCE'}
                </div>
            </div>
            <div style="margin-top: 10px; padding: 8px; background-color: ${result.is_speech ? '#d4edda' : '#f8f9fa'}; border-radius: 4px;">
                <strong>VAD Decision:</strong> ${result.is_speech ?
            'Voice activity detected using RMS + Spectral Flatness + ZCR analysis' :
            'No voice activity detected - background noise/silence'}
            </div>
        `;
    }
    async startRecording() {
        try {
            // Request microphone access
            this.mediaStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    sampleRate: 44100,
                    channelCount: 1,
                    echoCancellation: true,
                    noiseSuppression: true
                }
            });
            // Create audio context
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 44100
            });
            // Create audio source
            this.audioInput = this.audioContext.createMediaStreamSource(this.mediaStream);
            // Create script processor for audio processing
            const bufferSize = 2048; // This gives us ~46ms at 44.1kHz
            this.analyser = this.audioContext.createScriptProcessor(bufferSize, 1, 1);
            // Process audio data
            this.analyser.onaudioprocess = (event) => {
                if (this.ws && this.ws.readyState === WebSocket.OPEN && this.isRecording) {
                    const inputData = event.inputBuffer.getChannelData(0);
                    // Convert Float32Array to regular array for JSON serialization
                    const audioData = Array.from(inputData);
                    // Send audio data to server
                    const message = {
                        type: 'audio',
                        buffer: audioData,
                        chunkSize: inputData.length,
                        sampleRate: this.audioContext.sampleRate
                    };
                    this.ws.send(JSON.stringify(message));
                    this.frameCount++;
                }
            };
            // Connect audio nodes
            this.audioInput.connect(this.analyser);
            this.analyser.connect(this.audioContext.destination);
            this.isRecording = true;
            this.updateStatus('Recording...', 'recording');
            this.startRecordingButton.disabled = true;
            this.stopRecordingButton.disabled = false;
            console.log('Started recording and streaming audio');
        }
        catch (error) {
            console.error('Error starting recording:', error);
            this.updateStatus('Recording Failed', 'error');
        }
    }
    stopRecording() {
        this.isRecording = false;
        // Stop audio processing
        if (this.analyser) {
            this.analyser.disconnect();
            this.analyser = null;
        }
        if (this.audioInput) {
            this.audioInput.disconnect();
            this.audioInput = null;
        }
        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }
        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach(track => track.stop());
            this.mediaStream = null;
        }
        this.updateStatus('Stopped', 'stopped');
        this.startRecordingButton.disabled = false;
        this.stopRecordingButton.disabled = true;
        console.log('Stopped recording');
    }
    updateStatus(message, status) {
        this.statusElement.textContent = message;
        this.statusElement.className = status;
    }
}
// Initialize the app when the page loads
document.addEventListener('DOMContentLoaded', () => {
    new AudioStreamingApp();
});
//# sourceMappingURL=app.js.map