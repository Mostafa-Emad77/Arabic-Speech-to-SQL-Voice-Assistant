import io
import os
from importlib.resources import files
from typing import Any

import sounddevice as sd
import soundfile as sf


def _resolve_reference_audio_file() -> str | None:
    env_ref_file = os.getenv("TTS_REF_FILE", "").strip()
    if env_ref_file:
        if os.path.exists(env_ref_file):
            return env_ref_file
        raise FileNotFoundError(f"TTS_REF_FILE does not exist: {env_ref_file}")

    package_ref_file = files("silma_tts").joinpath("infer/ref_audio_samples/ar.ref.24k.wav")
    package_ref_path = str(package_ref_file)
    if os.path.exists(package_ref_path):
        return package_ref_path

    return None


def _get_silma_context() -> dict[str, Any]:
    ref_file = _resolve_reference_audio_file()
    if not ref_file:
        raise FileNotFoundError(
            "Could not resolve SILMA reference audio. Set TTS_REF_FILE in your .env file."
        )

    ref_text_env = os.getenv("TTS_REF_TEXT", "").strip()
    ref_text = ref_text_env or None

    speed_env = os.getenv("TTS_SPEED", "1.0").strip()
    try:
        speed = float(speed_env)
    except ValueError:
        speed = 1.0

    return {
        "ref_file": ref_file,
        "ref_text": ref_text,
        "speed": speed,
    }


def _infer_speech(context: Any, model: Any, text: str) -> tuple[Any, int]:
    if not text or not text.strip():
        raise ValueError("Cannot generate TTS for empty text")
    if context is None or model is None:
        raise ValueError("SILMA TTS model is not initialized")

    ref_file = context.get("ref_file")
    ref_text = context.get("ref_text")
    speed = context.get("speed", 1.0)

    wav, sr, _ = model.infer(
        ref_file=ref_file,
        ref_text=ref_text,
        gen_text=text,
        speed=speed,
        file_wave=None,
        seed=None,
    )
    return wav, sr


def initialize_local_arabic_tts() -> tuple[Any | None, Any | None]:
    print("Loading SILMA Arabic TTS model...")
    try:
        from silma_tts.api import SilmaTTS

        context = _get_silma_context()
        model = SilmaTTS()
        return context, model
    except Exception as e:
        print(f"Error loading SILMA Arabic TTS model: {e}")
        return None, None


def generate_speech_with_local_model(processor: Any, model: Any, text: str) -> bool:
    try:
        print("Generating speech using SILMA Arabic TTS model...")
        audio_data, sample_rate = _infer_speech(processor, model, text)
        print("Playing response...")
        sd.play(audio_data, samplerate=sample_rate)
        sd.wait()
        return True
    except Exception as e:
        print(f"Error generating speech with local model: {e}")
        return False


def generate_speech_for_web(processor: Any, model: Any, text: str) -> bytes:
    try:
        print("Generating speech using SILMA Arabic TTS model...")
        audio_data, sample_rate = _infer_speech(processor, model, text)
        byte_io = io.BytesIO()
        sf.write(byte_io, audio_data, samplerate=sample_rate, format="WAV")
        byte_io.seek(0)
        return byte_io.getvalue()
    except Exception as e:
        print(f"Error generating speech: {e}")
        raise e
