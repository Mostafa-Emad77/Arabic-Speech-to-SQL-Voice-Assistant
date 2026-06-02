import logging
import os
import tempfile
from typing import Any

logger = logging.getLogger(__name__)


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_supertonic_context() -> dict[str, Any]:
    voice_name = os.getenv("TTS_VOICE", "M1").strip() or "M1"
    lang = os.getenv("TTS_LANG", "ar").strip() or "ar"
    auto_download = _parse_bool(os.getenv("TTS_AUTO_DOWNLOAD", "true"), default=True)

    return {
        "voice_name": voice_name,
        "lang": lang,
        "auto_download": auto_download,
    }


def _synthesize_to_wav_bytes(context: Any, model: Any, text: str) -> bytes:
    if not text or not text.strip():
        raise ValueError("Cannot generate TTS for empty text")
    if context is None or model is None:
        raise ValueError("Supertonic TTS model is not initialized")

    voice_style = context.get("voice_style")
    lang = context.get("lang", "ar")
    wav, _ = model.synthesize(text, voice_style=voice_style, lang=lang)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
        temp_path = tmp_file.name

    try:
        model.save_audio(wav, temp_path)
        with open(temp_path, "rb") as wav_file:
            return wav_file.read()
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def initialize_local_arabic_tts() -> tuple[Any | None, Any | None]:
    logger.info("Loading Supertonic-3 Arabic TTS model...")
    try:
        from supertonic import TTS

        context = _get_supertonic_context()
        model = TTS(auto_download=context["auto_download"])
        context["voice_style"] = model.get_voice_style(voice_name=context["voice_name"])
        return context, model
    except Exception as e:
        logger.error("Error loading Supertonic-3 Arabic TTS model: %s", e)
        return None, None


def generate_speech_for_web(processor: Any, model: Any, text: str) -> bytes:
    logger.info("Generating speech using Supertonic-3 Arabic TTS model...")
    return _synthesize_to_wav_bytes(processor, model, text)
