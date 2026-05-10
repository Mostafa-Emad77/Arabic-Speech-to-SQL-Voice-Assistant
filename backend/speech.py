import os
import tempfile
from typing import Any

import sounddevice as sd
import soundfile as sf


def record_audio(duration: int = 10, sample_rate: int = 16000) -> str:
    print("Recording... Speak now")
    audio_data = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1)
    sd.wait()
    print("Recording finished")

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    sf.write(temp_file.name, audio_data, sample_rate)
    return temp_file.name


def transcribe_audio(transcriber: Any, audio_file: str) -> str:
    try:
        with open(audio_file, "rb") as f:
            audio_content = f.read()

        result = transcriber.automatic_speech_recognition(
            audio_content,
            model="openai/whisper-large-v3",
        )

        os.unlink(audio_file)
        text = result["text"].strip() if isinstance(result, dict) else result.strip()
        return text
    except Exception as e:
        print(f"Error in transcription: {e}")
        if os.path.exists(audio_file):
            os.unlink(audio_file)
        return "لم أتمكن من فهم الكلام"
