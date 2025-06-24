#!/usr/bin/env python3
"""
Simple Speech Transcriber
Usage: python3 transcribe.py
Press Ctrl+Space to record, speak, press Ctrl+Space to transcribe
"""

import threading
import time
import logging
import tempfile
import os
import ssl
import certifi
from enum import Enum

# Fix SSL certificate verification
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

import urllib.request
ssl_context = ssl.create_default_context(cafile=certifi.where())
https_handler = urllib.request.HTTPSHandler(context=ssl_context)
opener = urllib.request.build_opener(https_handler)
urllib.request.install_opener(opener)

import sounddevice as sd
import whisper
import numpy as np
from scipy.io.wavfile import write
from pynput import keyboard
from pynput.keyboard import Key, Listener as KeyboardListener

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ensure ffmpeg is available
if '/opt/homebrew/bin' not in os.environ.get('PATH', ''):
    os.environ['PATH'] = '/opt/homebrew/bin:' + os.environ.get('PATH', '')

class State(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"

class SpeechTranscriber:
    def __init__(self):
        self.state = State.IDLE
        self.audio_data = []
        self.is_recording = False
        self._whisper_model = None
        self.keyboard_controller = keyboard.Controller()

    @property
    def whisper_model(self):
        if self._whisper_model is None:
            logger.info("Loading Whisper model...")
            self._whisper_model = whisper.load_model("base")
        return self._whisper_model

    def toggle_recording(self):
        if self.state == State.IDLE:
            self.start_recording()
        elif self.state == State.RECORDING:
            self.stop_recording()

    def start_recording(self):
        if self.state != State.IDLE:
            return

        self.state = State.RECORDING
        self.audio_data = []
        self.is_recording = True
        threading.Thread(target=self._record_audio, daemon=True).start()
        logger.info("🎤 Recording started...")

    def stop_recording(self):
        if self.state != State.RECORDING:
            return

        self.is_recording = False
        if not self.audio_data:
            self.state = State.IDLE
            return

        logger.info("🔄 Processing...")
        self.state = State.PROCESSING
        threading.Thread(target=self._transcribe_and_type, daemon=True).start()

    def _record_audio(self):
        with sd.InputStream(samplerate=16000, channels=1, dtype=np.float32,
                           callback=self._audio_callback) as stream:
            while self.is_recording:
                time.sleep(0.1)

    def _audio_callback(self, indata, frames, time, status):
        if self.is_recording:
            self.audio_data.extend(indata.flatten())

    def _transcribe_and_type(self):
        try:
            # Convert to audio file
            audio_array = np.array(self.audio_data, dtype=np.float32)
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=True) as temp_file:
                audio_int16 = (audio_array * 32767).astype(np.int16)
                write(temp_file.name, 16000, audio_int16)

                # Transcribe
                result = self.whisper_model.transcribe(temp_file.name)
                text = result["text"].strip()

                if text:
                    logger.info(f"✅ Transcribed: {text}")
                    self.keyboard_controller.type(text)
                else:
                    logger.warning("❌ No text detected")

        except Exception as e:
            logger.error(f"❌ Error: {e}")

        finally:
            self.state = State.IDLE
            logger.info("Ready for next recording...")

def main():
    print("🎤 Speech Transcriber")
    print("Press Ctrl+Space to record, Ctrl+C to quit")

    transcriber = SpeechTranscriber()

    # Track modifier keys
    ctrl_pressed = False

    def on_key_press(key):
        nonlocal ctrl_pressed
        if key == Key.ctrl_l or key == Key.ctrl_r:
            ctrl_pressed = True
        elif key == Key.space and ctrl_pressed:
            transcriber.toggle_recording()

    def on_key_release(key):
        nonlocal ctrl_pressed
        if key == Key.ctrl_l or key == Key.ctrl_r:
            ctrl_pressed = False

    listener = KeyboardListener(on_press=on_key_press, on_release=on_key_release)
    listener.start()

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    finally:
        listener.stop()

if __name__ == "__main__":
    main()