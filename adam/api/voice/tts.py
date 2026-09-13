"""Pluggable TTS abstraction."""

import logging
import shutil
import struct
import subprocess
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BaseTtsEngine(ABC):
    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def synthesize(self, text: str, language: str = 'hi') -> bytes:
        pass

class NullTtsEngine(BaseTtsEngine):
    def is_available(self) -> bool:
        return True

    def synthesize(self, text: str, language: str = 'hi') -> bytes:
        # Minimal valid 44-byte WAV header for empty PCM
        header = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF', 36, b'WAVE', b'fmt ', 16, 1, 1, 22050, 44100, 2, 16, b'data', 0
        )
        return header

class PiperTtsEngine(BaseTtsEngine):
    def is_available(self) -> bool:
        return shutil.which('piper') is not None

    def synthesize(self, text: str, language: str = 'hi') -> bytes:
        try:
            # Note: A real implementation would specify a model file
            process = subprocess.Popen(
                ['piper', '--output_raw'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            out, err = process.communicate(input=text.encode('utf-8'))
            return out
        except Exception as e:
            logger.error(f"Error synthesizing speech with piper: {e}")
            return NullTtsEngine().synthesize(text, language)

def get_tts_engine() -> BaseTtsEngine:
    engine_piper = PiperTtsEngine()
    if engine_piper.is_available():
        logger.info("Selected PiperTtsEngine for TTS")
        return engine_piper
    logger.info("Selected NullTtsEngine for TTS")
    return NullTtsEngine()
