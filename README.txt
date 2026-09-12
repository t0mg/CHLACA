================================================================================
💥 BOOM! CHLACA - cheap and lazy captions ("boom shakalaka!")
Desktop App for Animated Subtitles on Vertical YouTube Shorts & TikTok (9:16)
================================================================================

Version: 1.0.0
Platform: Windows 10 / 11 (64-bit)
License: MIT (See THIRD_PARTY_LICENSES.txt)

--------------------------------------------------------------------------------
1. QUICK START
--------------------------------------------------------------------------------
1. Double-click `CHLACA.exe` to start the application.
2. If Windows SmartScreen appears:
   Click "More info" -> "Run anyway" (this occurs because the executable is not
   digitally signed with an enterprise certificate).
3. Select your 9:16 vertical video file.
4. Choose your model (default "base" is recommended) and target words per caption.
5. Click "Generate Subtitles with On-Device AI".
6. Edit transcription, customize font / colors / safe zone in the Style tab.
7. Click "Export" to burn the animated subtitles directly into a new MP4 video!

--------------------------------------------------------------------------------
2. AI MODEL WEIGHTS (FIRST-RUN NOTE)
--------------------------------------------------------------------------------
CHLACA transcribes audio 100% on-device and offline.
The speech recognition engine uses OpenAI Whisper open weights via faster-whisper.

- On the very first transcription, CHLACA will automatically download the chosen
  model weights from Hugging Face:
    * tiny: ~75 MB (Fastest)
    * base: ~145 MB (Recommended balance)
    * small: ~480 MB (High accuracy)
    * medium: ~1.5 GB (Very high accuracy)
    * large-v3-turbo: ~1.6 GB (Best quality)

- Once downloaded, model weights are permanently cached locally on your machine
  at: `C:\Users\<YourUser>\.cache\huggingface\hub\`.
  Subsequent runs are 100% offline with zero internet access required.

- Fully Offline Mode: You can also place pre-downloaded model folders directly
  inside a `models\` folder next to `CHLACA.exe`.

--------------------------------------------------------------------------------
3. HARDWARE & GPU ACCELERATION
--------------------------------------------------------------------------------
- GPU (CUDA): If your computer has an NVIDIA GeForce / RTX graphics card, CHLACA
  automatically uses CUDA 12 hardware acceleration for both transcription and
  video encoding (NVENC). All required CUDA runtime DLLs are pre-bundled.
- CPU Fallback: If no NVIDIA GPU is present, CHLACA seamlessly falls back to
  multi-threaded CPU execution (int8 quantized Whisper + libx264 encoding).

--------------------------------------------------------------------------------
4. VERTICAL SAFE ZONE (SHORTS & TIKTOK)
--------------------------------------------------------------------------------
Vertical video platforms overlay UI elements (like/comment buttons on the right,
sound title and creator handle at the bottom, and search bar at the top).

- Use the "Shorts / TikTok (72%)" preset on the Vertical Position slider.
- Toggle the "Safe Area Overlay" button in the preview player to verify that your
  captions remain completely visible and unobstructed.

--------------------------------------------------------------------------------
5. LICENSES & CREDITS
--------------------------------------------------------------------------------
CHLACA bundles open-source components including FFmpeg (LGPL/GPL), faster-whisper
(MIT), CTranslate2 (MIT), Silero VAD (MIT), pywebview (BSD-3), and NVIDIA CUDA
runtime libraries.
Please see `THIRD_PARTY_LICENSES.txt` for full license and copyright details.
