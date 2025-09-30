#!/usr/bin/env python3
"""
Advanced Voice Activity Detection WebSocket Server
Uses RMS Energy + Spectral Flatness + Zero Crossing Rate for robust VAD
Sends VAD results back to UI for real-time display
"""

import asyncio
import websockets
import json
import base64
import numpy as np
from scipy import signal
from scipy.stats import entropy
import logging
from datetime import datetime
import math

# Custom JSON encoder for numpy types
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (bool, np.bool_)):
            return bool(obj)
        return super(NumpyEncoder, self).default(obj)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AdvancedVAD:
    def __init__(self):
        self.sample_rate = 16000  # Target sample rate for VAD
        self.frame_size_ms = 20   # Frame size in milliseconds
        self.frame_size_samples = int(self.sample_rate * self.frame_size_ms / 1000)
        
        # VAD parameters
        self.rms_threshold = 0.01
        self.zcr_threshold = 0.1
        self.spectral_flatness_threshold = 0.3  # Lower = more tonal (speech), Higher = more noisy
        
        # Hangover parameters
        self.hangover_frames = 12  # ~240ms at 20ms frames
        self.min_speech_frames = 3  # Minimum frames for speech
        
        # State tracking
        self.is_voice_active = False
        self.hangover_counter = 0
        self.speech_frame_count = 0
        self.frame_count = 0
        
        # FIXED: Better initial noise floor values and adaptation
        self.noise_floor_rms = 0.0001  # Much lower initial value
        self.noise_floor_zcr = 0.01    # Much lower initial value
        self.noise_floor_flatness = 0.1  # Much lower initial value
        self.adaptation_alpha = 0.95  # Smoothing factor for noise floor adaptation
        
        # Feature history for smoothing
        self.history_size = 10
        self.rms_history = []
        self.zcr_history = []
        self.flatness_history = []
        
        logger.info("Advanced VAD initialized with RMS + Spectral Flatness + ZCR")
        logger.info(f"Sample rate: {self.sample_rate}Hz")
        logger.info(f"Frame size: {self.frame_size_samples} samples ({self.frame_size_ms}ms)")
        logger.info("Using RMS Energy + Spectral Flatness + Zero Crossing Rate")
    
    def calculate_rms_energy(self, audio_frame):
        """Calculate RMS energy of the audio frame"""
        return np.sqrt(np.mean(audio_frame**2))
    
    def calculate_zero_crossing_rate(self, audio_frame):
        """Calculate zero crossing rate"""
        zero_crossings = np.sum(np.abs(np.diff(np.sign(audio_frame))))
        return zero_crossings / len(audio_frame)
    
    def calculate_spectral_flatness(self, audio_frame):
        """
        Calculate spectral flatness (Wiener entropy)
        Lower values indicate more tonal content (speech)
        Higher values indicate more noisy content
        """
        # Apply window function
        windowed = audio_frame * signal.windows.hann(len(audio_frame))
        
        # Compute FFT
        fft = np.fft.fft(windowed)
        magnitude = np.abs(fft[:len(fft)//2])
        
        # Avoid log(0) by adding small epsilon
        magnitude = magnitude + 1e-10
        
        # Calculate geometric mean
        geometric_mean = np.exp(np.mean(np.log(magnitude)))
        
        # Calculate arithmetic mean
        arithmetic_mean = np.mean(magnitude)
        
        # Spectral flatness
        if arithmetic_mean > 0:
            return geometric_mean / arithmetic_mean
        else:
            return 0.0
    
    def process_frame(self, audio_frame):
        """Process a single audio frame and return VAD decision"""
        self.frame_count += 1
        
        # Calculate features
        rms = self.calculate_rms_energy(audio_frame)
        zcr = self.calculate_zero_crossing_rate(audio_frame)
        flatness = self.calculate_spectral_flatness(audio_frame)
        
        # Add to history for smoothing
        self.rms_history.append(rms)
        self.zcr_history.append(zcr)
        self.flatness_history.append(flatness)
        
        # Keep history size manageable
        if len(self.rms_history) > self.history_size:
            self.rms_history.pop(0)
            self.zcr_history.pop(0)
            self.flatness_history.pop(0)
        
        # Calculate smoothed features
        smoothed_rms = np.mean(self.rms_history)
        smoothed_zcr = np.mean(self.zcr_history)
        smoothed_flatness = np.mean(self.flatness_history)
        
        # FIXED: Always adapt noise floors during silence (not just first few frames)
        if not self.is_voice_active and self.hangover_counter == 0:
            # Only update noise floors during actual silence (not hangover)
            self.noise_floor_rms = self.adaptation_alpha * self.noise_floor_rms + (1 - self.adaptation_alpha) * smoothed_rms
            self.noise_floor_zcr = self.adaptation_alpha * self.noise_floor_zcr + (1 - self.adaptation_alpha) * smoothed_zcr
            self.noise_floor_flatness = self.adaptation_alpha * self.noise_floor_flatness + (1 - self.adaptation_alpha) * smoothed_flatness
            
            # Ensure noise floors don't go too extreme
            self.noise_floor_rms = max(0.0001, self.noise_floor_rms)
            self.noise_floor_zcr = np.clip(self.noise_floor_zcr, 0.01, 0.9)
            self.noise_floor_flatness = np.clip(self.noise_floor_flatness, 0.01, 0.99)
        
        # Multi-feature VAD decision with adaptive thresholds
        rms_decision = smoothed_rms > (self.noise_floor_rms * 2.0)  # 2x noise floor
        zcr_decision = smoothed_zcr > (self.noise_floor_zcr * 1.5)  # 1.5x noise floor
        flatness_decision = smoothed_flatness < (self.noise_floor_flatness * 0.8)  # Lower flatness = more speech-like
        
        # Combine decisions (majority vote)
        decisions = [rms_decision, zcr_decision, flatness_decision]
        speech_votes = sum(decisions)
        
        # Require at least 2 out of 3 features to indicate speech
        is_speech_detected = speech_votes >= 2
        
        # Apply hangover logic
        if is_speech_detected:
            self.speech_frame_count += 1
            if self.speech_frame_count >= self.min_speech_frames:
                self.hangover_counter = self.hangover_frames
        else:
            self.speech_frame_count = 0
        
        # Update voice activity state
        if self.hangover_counter > 0:
            self.is_voice_active = True
            self.hangover_counter -= 1
        else:
            self.is_voice_active = False
        
        # Prepare result - FIXED: Convert numpy types to Python types
        result = {
            "is_speech": bool(self.is_voice_active),
            "confidence": float(speech_votes / 3.0),
            "speech_votes": int(speech_votes),
            "frame_count": int(self.frame_count),
            "timestamp": datetime.now().isoformat(),
            "rms_energy": float(smoothed_rms),
            "rms_noise_floor": float(self.noise_floor_rms),
            "zcr": float(smoothed_zcr),
            "zcr_noise_floor": float(self.noise_floor_zcr),
            "spectral_flatness": float(smoothed_flatness),
            "flatness_noise_floor": float(self.noise_floor_flatness),
            "feature_decisions": {
                "rms": bool(rms_decision),
                "zcr": bool(zcr_decision),
                "spectral_flatness": bool(flatness_decision)
            },
            "vad_decision_reason": f"RMS={rms_decision}, ZCR={zcr_decision}, Flatness={flatness_decision}"
        }
        
        return result

async def audio_websocket_handler(websocket, path):
    """Handle WebSocket connections for audio streaming"""
    logger.info("Client connected")
    
    # Initialize VAD for this connection
    vad = AdvancedVAD()
    
    try:
        async for message in websocket:
            try:
                # Parse the audio data
                data = json.loads(message)
                audio_data = np.array(data['buffer'], dtype=np.float32)
                
                # Resample from 44.1kHz to 16kHz for VAD
                num_samples = len(audio_data)
                target_samples = int(num_samples * 16000 / 44100)
                resampled_audio = signal.resample(audio_data, target_samples)
                
                # Process the audio frame
                vad_result = vad.process_frame(resampled_audio)
                
                # Log the result
                status = "🎤 SPEECH DETECTED" if vad_result["is_speech"] else "🔇 SILENCE"
                logger.info(f"Frame {vad_result['frame_count']} ({vad_result['timestamp']}):")
                logger.info(f"  {status} - Confidence: {vad_result['confidence']:.3f}")
                logger.info(f"  RMS Energy: {vad_result['rms_energy']:.6f}, Noise Floor: {vad_result['rms_noise_floor']:.6f}")
                logger.info(f"  ZCR: {vad_result['zcr']:.3f}, Noise Floor: {vad_result['zcr_noise_floor']:.3f}")
                logger.info(f"  Spectral Flatness: {vad_result['spectral_flatness']:.3f}, Noise Floor: {vad_result['flatness_noise_floor']:.3f}")
                logger.info(f"  Speech Votes: {vad_result['speech_votes']}/3")
                logger.info(f"  Feature Decisions: RMS={vad_result['feature_decisions']['rms']}, ZCR={vad_result['feature_decisions']['zcr']}, Flatness={vad_result['feature_decisions']['spectral_flatness']}")
                logger.info(f"  VAD Decision Reason: {vad_result['vad_decision_reason']}")
                logger.info("---")
                
                # Send result back to frontend
                await websocket.send(json.dumps(vad_result, cls=NumpyEncoder))
                
            except json.JSONDecodeError:
                logger.error("Failed to parse JSON message")
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                
    except websockets.exceptions.ConnectionClosedOK:
        logger.info("Client disconnected gracefully")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")

async def main():
    """Main function to start the WebSocket server"""
    logger.info("Starting Advanced VAD WebSocket Server...")
    logger.info("Using multi-feature signal processing for robust VAD")
    
    try:
        # Start the WebSocket server
        start_server = websockets.serve(audio_websocket_handler, "0.0.0.0", 3001)
        logger.info("Server started on ws://localhost:3001")
        
        # Run the server
        await start_server
        await asyncio.Future()  # Run forever
        
    except Exception as e:
        logger.error(f"Server error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
