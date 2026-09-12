"""Build script for packaging CHLACA into a standalone Windows directory and installer.

Requirements:
    pip install pyinstaller  (or: uv pip install pyinstaller)

Usage:
    python packaging/build_windows.py
"""

import os
import sys
import shutil
import subprocess
import importlib.util

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def find_binary_in_path(name: str):
    """Find a binary in system PATH."""
    return shutil.which(name)

def ensure_venv_python():
    """Ensure the script runs inside the project virtual environment where packages are installed."""
    venv_python = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
    current_python = os.path.abspath(sys.executable).lower()
    
    if os.path.isfile(venv_python) and current_python != os.path.abspath(venv_python).lower():
        print(f"[*] Detected project virtualenv at: {venv_python}")
        print("[*] Re-executing packaging under .venv Python to include all dependencies...\n")
        res = subprocess.run([venv_python, os.path.abspath(__file__)] + sys.argv[1:])
        sys.exit(res.returncode)

def bundle_cuda_dlls(dist_dir: str):
    """Copy NVIDIA cuBLAS / cuDNN runtime DLLs into the bundled _internal directory for GPU acceleration."""
    internal_dir = os.path.join(dist_dir, "_internal")
    target_dir = internal_dir if os.path.isdir(internal_dir) else dist_dir

    nvidia_bin_dirs = []
    # Discover from current python environment
    try:
        import site
        site_dirs = []
        try:
            site_dirs.extend(site.getsitepackages())
        except Exception:
            pass
        try:
            site_dirs.append(site.getusersitepackages())
        except Exception:
            pass

        for sp in site_dirs:
            if not sp or not os.path.isdir(sp):
                continue
            nvidia_base = os.path.join(sp, "nvidia")
            if os.path.isdir(nvidia_base):
                for pkg in ["cublas", "cudnn", "cuda_nvrtc"]:
                    bin_dir = os.path.join(nvidia_base, pkg, "bin")
                    if os.path.isdir(bin_dir) and bin_dir not in nvidia_bin_dirs:
                        nvidia_bin_dirs.append(bin_dir)
    except Exception as e:
        print(f"[!] Note while probing CUDA DLLs: {e}")

    copied = 0
    for bdir in nvidia_bin_dirs:
        for fname in os.listdir(bdir):
            if fname.lower().endswith(".dll"):
                src = os.path.join(bdir, fname)
                dst = os.path.join(target_dir, fname)
                if not os.path.exists(dst):
                    try:
                        shutil.copy2(src, dst)
                        copied += 1
                    except Exception as ce:
                        print(f"[!] Could not copy {fname}: {ce}")
    if copied > 0:
        print(f"[OK] Bundled {copied} NVIDIA CUDA runtime DLL(s) for on-device GPU acceleration.")

def build():
    ensure_venv_python()
    os.chdir(PROJECT_ROOT)
    print("==================================================")
    print("[CHLACA] - Windows Packaging")
    print("==================================================")
    print(f"[*] Python executable: {sys.executable}")
    print(f"[*] Project root: {PROJECT_ROOT}")

    # 0. Terminate any running CHLACA instance to avoid file locks
    try:
        subprocess.run(["taskkill", "/F", "/IM", "CHLACA.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    # 1. Check / Install PyInstaller
    try:
        import PyInstaller
        print(f"[OK] PyInstaller detected (version {PyInstaller.__version__})")
    except ImportError:
        print("[!] PyInstaller not found. Installing via uv/pip...")
        if shutil.which("uv"):
            subprocess.run(["uv", "pip", "install", "pyinstaller"], check=True)
        else:
            subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    # 2. Check core dependencies
    required_deps = ["bottle", "webview", "faster_whisper", "ctranslate2", "tokenizers", "huggingface_hub", "av"]
    missing = [pkg for pkg in required_deps if not importlib.util.find_spec(pkg)]
    if missing:
        print(f"\n[!] WARNING: Missing dependencies in current environment: {', '.join(missing)}")
        print("    Please install with: uv pip install -e . (or pip install -e .)")
        sys.exit(1)

    # 3. Prepare PyInstaller command
    entry_script = os.path.join(PROJECT_ROOT, "run_chlaca.py")
    gui_data = f"{os.path.join(PROJECT_ROOT, 'piccut', 'gui')};piccut/gui"

    hidden_imports = [
        "bottle",
        "webview",
        "faster_whisper",
        "ctranslate2",
        "tokenizers",
        "huggingface_hub",
        "av",
        "certifi",
        "clr_loader",
        "pythonnet",
    ]

    hidden_args = []
    for h in hidden_imports:
        hidden_args.extend(["--hidden-import", h])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "CHLACA",
        "--add-data", gui_data,
        "--collect-all", "faster_whisper",
        *hidden_args,
        entry_script
    ]

    print(f"\n[*] Running PyInstaller build...")
    subprocess.run(cmd, check=True)
    dist_dir = os.path.join(PROJECT_ROOT, "dist", "CHLACA")
    print(f"[OK] Application bundled into: {dist_dir}")

    # 4. Bundle FFmpeg if available
    ffmpeg_exe = find_binary_in_path("ffmpeg")
    ffprobe_exe = find_binary_in_path("ffprobe")
    if ffmpeg_exe and os.path.isfile(ffmpeg_exe):
        dest_ffmpeg = os.path.join(dist_dir, "ffmpeg.exe")
        shutil.copy2(ffmpeg_exe, dest_ffmpeg)
        print(f"[OK] Bundled ffmpeg.exe from {ffmpeg_exe}")
    if ffprobe_exe and os.path.isfile(ffprobe_exe):
        dest_ffprobe = os.path.join(dist_dir, "ffprobe.exe")
        shutil.copy2(ffprobe_exe, dest_ffprobe)
        print(f"[OK] Bundled ffprobe.exe from {ffprobe_exe}")

    # 5. Bundle CUDA runtime DLLs (cuBLAS, cuDNN)
    bundle_cuda_dlls(dist_dir)

    # 6. Ensure faster-whisper assets (silero_vad_v6.onnx) are bundled
    try:
        import faster_whisper
        fw_dir = os.path.dirname(faster_whisper.__file__)
        fw_assets_src = os.path.join(fw_dir, "assets")
        fw_assets_dst = os.path.join(dist_dir, "_internal", "faster_whisper", "assets")
        if os.path.isdir(fw_assets_src):
            os.makedirs(fw_assets_dst, exist_ok=True)
            for fname in os.listdir(fw_assets_src):
                s = os.path.join(fw_assets_src, fname)
                d = os.path.join(fw_assets_dst, fname)
                if os.path.isfile(s):
                    shutil.copy2(s, d)
            print(f"[OK] Bundled faster-whisper assets (Silero VAD) into {fw_assets_dst}")
    except Exception as e:
        print(f"[!] Note while bundling faster-whisper assets: {e}")

    # 7. Copy documentation and licenses
    for doc_name in ["README.txt", "THIRD_PARTY_LICENSES.txt", "LICENSE"]:
        src_doc = os.path.join(PROJECT_ROOT, doc_name)
        if os.path.isfile(src_doc):
            shutil.copy2(src_doc, os.path.join(dist_dir, doc_name))
            print(f"[OK] Bundled document: {doc_name}")

    # 8. Check for Inno Setup compiler
    inno_paths = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        shutil.which("ISCC.exe")
    ]
    iscc = next((p for p in inno_paths if p and os.path.isfile(p)), None)

    iss_file = os.path.join(PROJECT_ROOT, "packaging", "CHLACA_installer.iss")
    if iscc and os.path.isfile(iss_file):
        print(f"\n[*] Inno Setup Compiler found: {iscc}")
        print(f"[*] Compiling setup installer...")
        subprocess.run([iscc, iss_file], check=True)
        print("[SUCCESS] Windows installer compiled in dist/ directory!")
    else:
        print("\n[NOTE] Inno Setup (ISCC.exe) not found on system.")
        print("To create a single .exe installer, install Inno Setup: winget install JRSoftware.InnoSetup")
        print(f"and re-run, or compile 'packaging/CHLACA_installer.iss'.")

    # 8. Create ZIP archive if requested or automatically
    if "--zip" in sys.argv:
        create_portable_zip()

def create_portable_zip():
    """Create a portable zip archive of dist/CHLACA."""
    dist_chlac = os.path.join(PROJECT_ROOT, "dist", "CHLACA")
    if not os.path.isdir(dist_chlac):
        print(f"[!] Cannot create zip: {dist_chlac} does not exist. Run build first.")
        return
    zip_base = os.path.join(PROJECT_ROOT, "dist", "CHLACA-portable-windows-x64")
    print(f"\n[*] Compressing portable ZIP archive: {zip_base}.zip ...")
    shutil.make_archive(zip_base, "zip", root_dir=os.path.join(PROJECT_ROOT, "dist"), base_dir="CHLACA")
    zip_file = f"{zip_base}.zip"
    size_mb = os.path.getsize(zip_file) / (1024 * 1024)
    print(f"[SUCCESS] Created portable archive ({size_mb:.1f} MB): {zip_file}")

if __name__ == "__main__":
    if "--zip-only" in sys.argv:
        ensure_venv_python()
        create_portable_zip()
    else:
        build()


