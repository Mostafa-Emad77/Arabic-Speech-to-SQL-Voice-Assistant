import logging
import os
from typing import Any

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


def initialize_asr_model() -> Any | None:
    logger.info("Loading faster-whisper ASR model...")
    model_name = os.getenv("ASR_MODEL", "large-v3-turbo")
    device = os.getenv("ASR_DEVICE", "cuda")
    compute_type = os.getenv("ASR_COMPUTE_TYPE", "int8_float16")

    try:
        return WhisperModel(model_name, device=device, compute_type=compute_type)
    except Exception as e:
        logger.error("Error loading faster-whisper model: %s", e)
        return None


def transcribe_audio(transcriber: Any, audio_file: str) -> str:
    try:
        if transcriber is None:
            return "لم أتمكن من فهم الكلام"

        beam_size = int(os.getenv("ASR_BEAM_SIZE", "5"))
        segments, _ = transcriber.transcribe(audio_file, language="ar", beam_size=beam_size)
        text = " ".join(segment.text.strip() for segment in segments if segment.text).strip()
        return text or "لم أتمكن من فهم الكلام"
    except Exception as e:
        logger.error("Error in transcription: %s", e)
        return "لم أتمكن من فهم الكلام"
