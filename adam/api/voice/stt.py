"""Pluggable STT abstraction."""

import importlib.util
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class SttResult:
    transcript: str
    language: str
    confidence: float

class BaseSttEngine(ABC):
    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def transcribe(self, audio_bytes: bytes, language_hint: str = 'hi') -> SttResult:
        pass

class FasterWhisperEngine(BaseSttEngine):
    def is_available(self) -> bool:
        return importlib.util.find_spec('faster_whisper') is not None

    def transcribe(self, audio_bytes: bytes, language_hint: str = 'hi') -> SttResult:
        try:
            from faster_whisper import WhisperModel
            import io
            
            # Write bytes to file-like object
            audio_io = io.BytesIO(audio_bytes)
            
            # Lazy load model
            model = WhisperModel("small", device="cpu", compute_type="int8")
            segments, info = model.transcribe(audio_io, language=language_hint)
            
            transcript = " ".join([segment.text for segment in segments])
            language = info.language
            
            return SttResult(
                transcript=transcript.strip(),
                language=language,
                confidence=0.8  # Default confidence fallback
            )
        except ImportError:
            logger.error("faster_whisper is not installed")
            return SttResult(transcript="", language=language_hint, confidence=0.0)
        except Exception as e:
            logger.error(f"Error during transcription: {e}")
            return SttResult(transcript="", language=language_hint, confidence=0.0)

class NullSttEngine(BaseSttEngine):
    def is_available(self) -> bool:
        return True

    def transcribe(self, audio_bytes: bytes, language_hint: str = 'hi') -> SttResult:
        return SttResult(transcript='', language='hi', confidence=0.0)

def get_stt_engine() -> BaseSttEngine:
    engine_fw = FasterWhisperEngine()
    if engine_fw.is_available():
        logger.info("Selected FasterWhisperEngine for STT")
        return engine_fw
    logger.info("Selected NullSttEngine for STT")
    return NullSttEngine()
