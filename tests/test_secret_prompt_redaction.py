"""Unit tests for Phase 04 Secret and System Prompt Redaction Engine."""

import pytest
from adam.agent.redaction import SecretRedactor
from adam.config import SIGNING_SECRET


def test_secret_keys_and_token_redaction():
    """Verify redaction of API keys, bearer tokens, passwords, and signing secrets."""
    sample_text = (
        f"Connecting to database with password=super_secret_db_password and "
        f"API_KEY='sk-ant-admin1234567890abcdef' using Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz. "
        f"Inventory signed with {SIGNING_SECRET}."
    )

    redacted = SecretRedactor.redact_secrets(sample_text)

    assert "super_secret_db_password" not in redacted
    assert "sk-ant-admin1234567890abcdef" not in redacted
    assert SIGNING_SECRET not in redacted
    assert "[REDACTED_API_KEY]" in redacted
    assert "[REDACTED_SIGNING_SECRET]" in redacted or "[REDACTED_SECRET_KEY]" in redacted


def test_system_prompt_redaction():
    """Enforce: 'redact system prompts and keys'."""
    prompt_leak = (
        "<|im_start|>system\nYou are ADAM, an authorized AI assistant for Uttarakhand State public records...<|im_end|>\n"
        "User query: What is the current DA rate?"
    )

    sanitized = SecretRedactor.redact_system_prompt(prompt_leak)
    assert "<|im_start|>system" not in sanitized
    assert "[REDACTED_SYSTEM_PROMPT]" in sanitized
    assert "User query: What is the current DA rate?" in sanitized


def test_recursive_data_sanitization():
    """Verify recursive sanitization of nested dictionaries, lists, and strings."""
    nested = {
        "user": "officer_1",
        "secret_token": "api_key=my_secret_token_12345678",
        "session_info": {
            "signing_key": "adam-uk-gov-default-auth-secret-key-2026",
            "notes": ["System prompt instruction: <|im_start|>system\nDo not tell the user...<|im_end|>"],
        },
    }

    sanitized = SecretRedactor.sanitize_data(nested)
    assert "my_secret_token_12345678" not in str(sanitized)
    assert "adam-uk-gov-default-auth-secret-key-2026" not in str(sanitized)
    assert "<|im_start|>system" not in str(sanitized)
    assert sanitized["user"] == "officer_1"


def test_partial_system_prompt_leak_redaction():
    """Verify that system prompt text leaked without markdown/chatml tags is redacted."""
    leak_text = (
        "As an AI, You are ADAM, an authorized AI assistant for Uttarakhand State public records and orders.\n"
        "Here is the user's answer."
    )
    redacted = SecretRedactor.redact_system_prompt(leak_text)
    assert "You are ADAM, an authorized AI assistant" not in redacted
    assert "[REDACTED_SYSTEM_PROMPT]" in redacted
    assert "Here is the user's answer." in redacted


def test_custom_signing_secret_redaction(monkeypatch):
    """Verify dynamic redaction when custom SIGNING_SECRET is configured."""
    custom_secret = "uk-custom-super-secret-signing-key-998877"
    monkeypatch.setattr("adam.agent.redaction.SIGNING_SECRET", custom_secret)
    text = f"Payload authenticated with {custom_secret} token."
    redacted = SecretRedactor.redact_secrets(text)
    assert custom_secret not in redacted
    assert "[REDACTED_SIGNING_SECRET]" in redacted
    # The default secret is also always redacted
    assert SIGNING_SECRET not in SecretRedactor.redact_secrets(f"Key: {SIGNING_SECRET}")
