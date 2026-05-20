import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _load_env() -> None:
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")


def check_whisper_model(allow_download: bool) -> tuple[bool, str]:
    model_name = os.getenv("ASR_MODEL", "large-v3-turbo")
    device = os.getenv("ASR_DEVICE", "cuda")
    compute_type = os.getenv("ASR_COMPUTE_TYPE", "int8_float16")

    try:
        from faster_whisper import WhisperModel

        try:
            WhisperModel(
                model_name,
                device=device,
                compute_type=compute_type,
                local_files_only=not allow_download,
            )
        except TypeError:
            # Older faster-whisper releases may not support local_files_only.
            if not allow_download:
                return (
                    False,
                    "Installed faster-whisper does not support local_files_only; rerun with --allow-download.",
                )
            WhisperModel(model_name, device=device, compute_type=compute_type)

        return True, f"Whisper model ready: {model_name} ({device}, {compute_type})"
    except Exception as exc:
        return False, f"Whisper model check failed: {exc}"


def check_tts_model(allow_download: bool) -> tuple[bool, str]:
    lang = os.getenv("TTS_LANG", "ar")
    voice = os.getenv("TTS_VOICE", "M1")

    try:
        from supertonic import TTS

        tts = TTS(auto_download=allow_download)
        _ = tts.get_voice_style(voice_name=voice)
        return True, f"Supertonic TTS ready: voice={voice}, lang={lang}"
    except Exception as exc:
        return False, f"Supertonic TTS check failed: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check ASR/TTS model availability before starting the backend."
    )
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="Allow model download during checks (useful on first setup).",
    )
    args = parser.parse_args()

    _load_env()

    print("Running model prestart checks...")
    whisper_ok, whisper_msg = check_whisper_model(allow_download=args.allow_download)
    print(("[OK] " if whisper_ok else "[FAIL] ") + whisper_msg)

    tts_ok, tts_msg = check_tts_model(allow_download=args.allow_download)
    print(("[OK] " if tts_ok else "[FAIL] ") + tts_msg)

    if whisper_ok and tts_ok:
        print("All model checks passed.")
        return 0

    print("Model checks failed. Fix issues above before starting backend.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
