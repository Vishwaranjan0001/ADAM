"""Unit tests for conversation memory field encryption engine."""

import pytest

from adam.memory.crypto import AuthenticatedCipher, MemoryCryptoError


def test_authenticated_cipher_roundtrip():
    """Verify encryption and decryption roundtrip for ASCII and Devanagari Hindi text."""
    cipher = AuthenticatedCipher(b"test-secret-key-1234567890")
    
    # ASCII text
    plaintext = "What is the procedure for vehicle advance reimbursement?"
    token = cipher.encrypt(plaintext)
    assert token != plaintext
    assert isinstance(token, str)
    decrypted = cipher.decrypt(token)
    assert decrypted == plaintext

    # Devanagari Hindi text
    hindi_text = "शासनादेश संख्या 123/XXVII(7)/2022 वाहन अग्रिम नियम"
    hindi_token = cipher.encrypt(hindi_text)
    assert hindi_token != hindi_text
    assert cipher.decrypt(hindi_token) == hindi_text


def test_cipher_json_serialization():
    """Verify JSON data structure encryption and decryption."""
    cipher = AuthenticatedCipher(b"test-secret-key-1234567890")
    data = {
        "query_intents": ["VEHICLE_ADVANCE"],
        "selected_filters": {"department_id": "FINANCE_TREASURY", "year": 2024},
        "citations_opened": ["chk_12345", "chk_67890"],
        "user_corrections": ["Actually referring to Class II officers"],
    }
    token = cipher.encrypt_json(data)
    recovered = cipher.decrypt_json(token)
    assert recovered == data


def test_tamper_detection_fails():
    """Verify that tampering with IV, tag, or ciphertext raises MemoryCryptoError."""
    import base64

    cipher = AuthenticatedCipher(b"test-secret-key-1234567890")
    token = cipher.encrypt("Confidential administrative memorandum")

    raw = bytearray(base64.b64decode(token.encode("ascii")))
    # Tamper with the last byte of ciphertext
    raw[-1] ^= 0xFF
    tampered_token = base64.b64encode(bytes(raw)).decode("ascii")

    with pytest.raises(MemoryCryptoError, match="Integrity check failed"):
        cipher.decrypt(tampered_token)


def test_truncated_token_rejection():
    """Verify truncated or malformed tokens are rejected."""
    cipher = AuthenticatedCipher(b"test-secret-key-1234567890")
    with pytest.raises(MemoryCryptoError):
        cipher.decrypt("dHJ1bmNhdGVk")  # "truncated" in base64 (too short)
