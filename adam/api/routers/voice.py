"""Voice endpoints."""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from adam.api.voice.stt import FasterWhisperEngine, get_stt_engine
from adam.api.voice.tts import get_tts_engine

router = APIRouter()

class SynthesizeRequest(BaseModel):
    text: str
    language: str = 'hi'

@router.post("/voice/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language_hint: str = Form("hi"),
):
    audio_bytes = await file.read()
    stt_engine = get_stt_engine()
    if not isinstance(stt_engine, FasterWhisperEngine):
        raise HTTPException(
            status_code=503,
            detail="Speech-to-text is unavailable: install the 'voice' dependencies (faster-whisper) and restart ADAM.",
        )
    result = stt_engine.transcribe(audio_bytes, language_hint=language_hint)
    if not result.transcript:
        raise HTTPException(
            status_code=502,
            detail="Fast Whisper could not transcribe this recording. Check the microphone recording and try again.",
        )
    return {
        "transcript": result.transcript,
        "language": result.language,
        "confidence": result.confidence
    }

@router.post("/voice/synthesize")
def synthesize_speech(req: SynthesizeRequest):
    tts_engine = get_tts_engine()
    wav_bytes = tts_engine.synthesize(req.text, req.language)
    return Response(content=wav_bytes, media_type='audio/wav')
