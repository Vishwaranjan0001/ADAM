"""Authenticated encryption engine for conversation memory at rest.

Provides field-level encryption for conversational turns, session summaries,
and user preferences using standard-library cryptography (SHA-256 CTR keystream
with HMAC-SHA256 Encrypt-then-MAC). Zero external C-dependencies required.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
from typing import Any, Optional

from adam.config import SIGNING_SECRET


class MemoryCryptoError(Exception):
    """Raised when encryption or decryption fails (e.g., tampering, corrupt ciphertext)."""
    pass


class AuthenticatedCipher:
    """Authenticated field-level cipher using Encrypt-then-MAC.

    Format of encrypted token:
        Base64( IV [16 bytes] + HMAC_TAG [32 bytes] + CIPHERTEXT [N bytes] )
    """

    def __init__(self, key: Optional[bytes] = None):
        raw_key = key or os.environ.get("MEMORY_ENCRYPTION_KEY", SIGNING_SECRET).encode("utf-8")
        # Derive separate 16-byte encryption key and 16-byte MAC key
        derived = hashlib.sha256(raw_key).digest()
        self._enc_key = derived[:16]
        self._mac_key = derived[16:]

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext string into base64 authenticated ciphertext token."""
        if not isinstance(plaintext, str):
            raise TypeError("Plaintext must be a string")

        data = plaintext.encode("utf-8")
        iv = secrets.token_bytes(16)

        # Keystream via SHA-256 CTR mode
        keystream = b""
        counter = 0
        while len(keystream) < len(data):
            keystream += hashlib.sha256(self._enc_key + iv + counter.to_bytes(4, "big")).digest()
            counter += 1

        ciphertext = bytes(a ^ b for a, b in zip(data, keystream[:len(data)]))
        # Encrypt-then-MAC: authenticate both IV and ciphertext
        tag = hmac.new(self._mac_key, iv + ciphertext, hashlib.sha256).digest()

        return base64.b64encode(iv + tag + ciphertext).decode("ascii")

    def decrypt(self, token: str) -> str:
        """Decrypt base64 token and verify integrity. Raises MemoryCryptoError on tampering."""
        if not isinstance(token, str):
            raise TypeError("Token must be a string")

        try:
            raw = base64.b64decode(token.encode("ascii"))
        except Exception as e:
            raise MemoryCryptoError(f"Invalid base64 encoding: {e}") from e

        if len(raw) < 48:  # 16 bytes IV + 32 bytes HMAC tag
            raise MemoryCryptoError("Ciphertext payload is truncated or invalid")

        iv = raw[:16]
        tag = raw[16:48]
        ciphertext = raw[48:]

        # Verify HMAC tag in constant time
        expected_tag = hmac.new(self._mac_key, iv + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected_tag):
            raise MemoryCryptoError("Integrity check failed: ciphertext has been modified or wrong key")

        # Regenerate keystream
        keystream = b""
        counter = 0
        while len(keystream) < len(ciphertext):
            keystream += hashlib.sha256(self._enc_key + iv + counter.to_bytes(4, "big")).digest()
            counter += 1

        data = bytes(a ^ b for a, b in zip(ciphertext, keystream[:len(ciphertext)]))
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise MemoryCryptoError(f"Decoded data is not valid UTF-8: {e}") from e

    def encrypt_json(self, data: Any) -> str:
        """Serialize data to JSON and encrypt."""
        return self.encrypt(json.dumps(data, ensure_ascii=False))

    def decrypt_json(self, token: str) -> Any:
        """Decrypt token and parse as JSON."""
        plaintext = self.decrypt(token)
        try:
            return json.loads(plaintext)
        except json.JSONDecodeError as e:
            raise MemoryCryptoError(f"Decrypted text is not valid JSON: {e}") from e


_DEFAULT_CIPHER: Optional[AuthenticatedCipher] = None


def get_cipher() -> AuthenticatedCipher:
    """Singleton getter for default memory cipher."""
    global _DEFAULT_CIPHER
    if _DEFAULT_CIPHER is None:
        _DEFAULT_CIPHER = AuthenticatedCipher()
    return _DEFAULT_CIPHER


def reset_cipher():
    """Reset cipher singleton (useful for test isolation when keys change)."""
    global _DEFAULT_CIPHER
    _DEFAULT_CIPHER = None
