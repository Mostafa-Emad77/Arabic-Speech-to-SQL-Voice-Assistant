import io
from typing import Any

import sounddevice as sd
import soundfile as sf
import torch
from transformers import AutoProcessor, VitsModel


def initialize_local_arabic_tts() -> tuple[Any | None, Any | None]:
    print("Loading local Arabic TTS model...")
    try:
        model_name = "facebook/mms-tts-ara"
        processor = AutoProcessor.from_pretrained(model_name)
        model = VitsModel.from_pretrained(model_name)
        return processor, model
    except Exception as e:
        print(f"Error loading local Arabic TTS model: {e}")
        return None, None


def generate_speech_with_local_model(processor: Any, model: Any, text: str) -> bool:
    try:
        print("Generating speech using local Arabic TTS model...")
        inputs = processor(text=text, return_tensors="pt")
        with torch.no_grad():
            output = model(**inputs).waveform

        audio_data = output.squeeze().numpy()
        print("Playing response...")
        sd.play(audio_data, samplerate=model.config.sampling_rate)
        sd.wait()
        return True
    except Exception as e:
        print(f"Error generating speech with local model: {e}")
        return False


def generate_speech_for_web(processor: Any, model: Any, text: str) -> bytes:
    try:
        print("Generating speech using Arabic TTS model...")
        inputs = processor(text=text, return_tensors="pt")
        with torch.no_grad():
            output = model(**inputs).waveform

        audio_data = output.squeeze().numpy()
        byte_io = io.BytesIO()
        sf.write(byte_io, audio_data, samplerate=model.config.sampling_rate, format="WAV")
        byte_io.seek(0)
        return byte_io.getvalue()
    except Exception as e:
        print(f"Error generating speech: {e}")
        raise e
