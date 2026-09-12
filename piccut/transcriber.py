"""On-device audio/video transcription using faster-whisper (CTranslate2).
Produces exact word-level timestamps for animated subtitle generation.
Includes automatic NVIDIA CUDA runtime DLL discovery and robust CPU fallback.
"""

import os
import sys
import logging
from typing import List, Dict, Any, Optional, Callable
import ctranslate2

logger = logging.getLogger(__name__)

def setup_cuda_dlls():
    """Find and add NVIDIA CUDA / cuBLAS / cuDNN DLL directories to the Windows search path."""
    if sys.platform != "win32":
        return

    import site
    candidates = []
    
    # Check all site-packages directories (virtualenv + global)
    site_dirs = []
    try:
        site_dirs.extend(site.getsitepackages())
    except Exception:
        pass
    try:
        site_dirs.append(site.getusersitepackages())
    except Exception:
        pass

    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        bundle_dir = getattr(sys, "_MEIPASS", exe_dir)
        for base in [
            exe_dir,
            bundle_dir,
            os.path.join(exe_dir, "_internal"),
            os.path.join(bundle_dir, "_internal"),
            os.path.join(exe_dir, "_internal", "nvidia"),
            os.path.join(bundle_dir, "_internal", "nvidia"),
        ]:
            if os.path.isdir(base) and base not in candidates:
                candidates.append(base)

    for sp in site_dirs:
        if not sp or not os.path.isdir(sp):
            continue
        nvidia_base = os.path.join(sp, "nvidia")
        if os.path.isdir(nvidia_base):
            for pkg in ["cublas", "cudnn", "cuda_nvrtc", "cuda_runtime"]:
                bin_dir = os.path.join(nvidia_base, pkg, "bin")
                if os.path.isdir(bin_dir) and bin_dir not in candidates:
                    candidates.append(bin_dir)

    for d in candidates:
        try:
            os.add_dll_directory(d)
        except Exception:
            pass
        if d not in os.environ.get("PATH", ""):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")

# Run DLL setup on module load
setup_cuda_dlls()

AVAILABLE_MODELS = [
    {"id": "tiny", "name": "Whisper Tiny (~75 MB, Fastest)", "size_mb": 75},
    {"id": "base", "name": "Whisper Base (~145 MB, Recommended for quick shorts)", "size_mb": 145},
    {"id": "small", "name": "Whisper Small (~480 MB, High Accuracy)", "size_mb": 480},
    {"id": "medium", "name": "Whisper Medium (~1.5 GB, Very High Accuracy)", "size_mb": 1500},
    {"id": "large-v3-turbo", "name": "Whisper Large-v3-Turbo (~1.6 GB, Best Quality & Speed)", "size_mb": 1600},
]

def get_model_download_root() -> Optional[str]:
    """Check if a local 'models' folder exists next to the executable or script."""
    base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local_models = os.path.join(base_dir, "models")
    if os.path.isdir(local_models):
        return local_models
    return None

def has_cuda_dlls() -> bool:
    """Check if cublas64_12.dll can be loaded or found on Windows."""
    if sys.platform != "win32":
        return True
    setup_cuda_dlls()
    import ctypes
    for name in ["cublas64_12.dll", "cublas64_11.dll"]:
        try:
            ctypes.CDLL(name)
            return True
        except Exception:
            continue
    return False

def get_available_devices() -> Dict[str, Any]:
    """Check system capabilities for GPU/CPU inference."""
    has_cuda_device = ctranslate2.get_cuda_device_count() > 0
    cuda_usable = has_cuda_device and has_cuda_dlls()
    return {
        "cuda_available": cuda_usable,
        "cuda_device_detected": has_cuda_device,
        "default_device": "cuda" if cuda_usable else "cpu",
        "default_compute_type": "float16" if cuda_usable else "int8",
    }

class Transcriber:
    def __init__(self, model_size: str = "base", device: Optional[str] = None, compute_type: Optional[str] = None):
        dev_info = get_available_devices()
        self.model_size = model_size

        if device:
            self.device = device
        else:
            self.device = dev_info["default_device"]
        
        if compute_type:
            self.compute_type = compute_type
        else:
            self.compute_type = "float16" if self.device == "cuda" else "int8"
            
        self._model = None

    def load_model(self, progress_callback: Optional[Callable[[str, int], None]] = None):
        """Loads the model, downloading open weights on demand if not cached."""
        from faster_whisper import WhisperModel
        
        if progress_callback:
            progress_callback(f"Loading/downloading Whisper model '{self.model_size}'...", 10)
        logger.info(f"Loading Whisper model {self.model_size} on {self.device} ({self.compute_type})...")
        
        try:
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                download_root=get_model_download_root()
            )
        except Exception as e:
            if self.device == "cuda":
                logger.warning(f"CUDA initialization failed ({e}). Falling back to CPU.")
                if progress_callback:
                    progress_callback("CUDA initialization failed. Falling back to CPU...", 12)
                self.device = "cpu"
                self.compute_type = "int8"
                self._model = WhisperModel(
                    self.model_size,
                    device="cpu",
                    compute_type="int8",
                    download_root=get_model_download_root()
                )
            else:
                raise e

    def transcribe(
        self,
        media_path: str,
        language: Optional[str] = None,
        vad_filter: bool = True,
        progress_callback: Optional[Callable[[str, int], None]] = None
    ) -> Dict[str, Any]:
        """Transcribe a video or audio file and return word-level timestamps.
        
        Includes automatic fallback to CPU if CUDA runtime libraries (cublas64_12.dll)
        fail to load at runtime, and automatic fallback if Silero VAD model is unavailable.
        """
        if not os.path.isfile(media_path):
            raise FileNotFoundError(f"Media file not found: {media_path}")

        from faster_whisper import WhisperModel

        if self._model is None:
            self.load_model(progress_callback)

        if progress_callback:
            progress_callback("Analyzing audio & transcribing with word timestamps...", 30)

        # Transcribe with word timestamps enabled
        try:
            transcribe_kwargs = {
                "language": language if language and language != "auto" else None,
                "word_timestamps": True,
                "vad_filter": vad_filter,
            }
            if vad_filter:
                transcribe_kwargs["vad_parameters"] = dict(min_silence_duration_ms=400)

            segments_gen, info = self._model.transcribe(
                media_path,
                **transcribe_kwargs
            )

            all_words: List[Dict[str, Any]] = []
            raw_segments: List[Dict[str, Any]] = []
            total_duration = info.duration if info.duration and info.duration > 0 else 1.0

            for seg in segments_gen:
                seg_words = []
                if seg.words:
                    for w in seg.words:
                        word_clean = w.word.strip()
                        if not word_clean:
                            continue
                        word_data = {
                            "word": word_clean,
                            "start": round(w.start, 3),
                            "end": round(w.end, 3),
                            "probability": round(w.probability, 3)
                        }
                        all_words.append(word_data)
                        seg_words.append(word_data)

                raw_segments.append({
                    "id": seg.id,
                    "start": round(seg.start, 3),
                    "end": round(seg.end, 3),
                    "text": seg.text.strip(),
                    "words": seg_words
                })

                if progress_callback and seg.end:
                    pct = min(95, int(30 + (seg.end / total_duration) * 65))
                    progress_callback(f"Transcribing... ({int(seg.end)}s / {int(total_duration)}s)", pct)

        except Exception as e:
            err_msg = str(e).lower()
            if vad_filter and any(k in err_msg for k in ["silero", "vad", "onnx", "no_suchfile"]):
                logger.warning(f"VAD model failed ({e}). Retrying transcription with vad_filter=False...")
                if progress_callback:
                    progress_callback("VAD model unavailable. Transcribing directly...", 30)
                return self.transcribe(
                    media_path,
                    language=language,
                    vad_filter=False,
                    progress_callback=progress_callback
                )

            if self.device == "cuda" and any(k in err_msg for k in ["cublas", "cudnn", "cuda", "cannot be loaded", "not found"]):
                logger.warning(f"CUDA execution failed ({e}). Automatically falling back to CPU (int8)...")
                if progress_callback:
                    progress_callback("CUDA libraries unavailable. Automatically falling back to CPU...", 20)
                
                # Re-initialize on CPU
                self.device = "cpu"
                self.compute_type = "int8"
                self._model = WhisperModel(
                    self.model_size,
                    device="cpu",
                    compute_type="int8"
                )
                # Re-run on CPU
                return self.transcribe(media_path, language=language, vad_filter=vad_filter, progress_callback=progress_callback)
            else:
                raise e

        if progress_callback:
            progress_callback("Transcription complete!", 100)

        return {
            "language": info.language,
            "language_probability": round(info.language_probability, 3) if info.language_probability else 1.0,
            "duration": round(total_duration, 3),
            "words": all_words,
            "raw_segments": raw_segments
        }
