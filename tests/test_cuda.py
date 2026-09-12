"""Test CUDA device detection and execution."""

import os
import pytest
from piccut.transcriber import Transcriber, get_available_devices, has_cuda_dlls

def test_cuda_detection():
    devs = get_available_devices()
    print("Detected devices:", devs)
    assert "default_device" in devs
    assert "cuda_available" in devs

def test_cuda_transcription_if_available():
    devs = get_available_devices()
    device = "cuda" if devs["cuda_available"] else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    
    t = Transcriber(model_size="tiny", device=device, compute_type=compute_type)
    res = t.transcribe("tests/fixtures/speech_sample.wav")
    assert len(res["words"]) > 0
    print(f"Transcribed {len(res['words'])} words on {t.device} ({t.compute_type})")
