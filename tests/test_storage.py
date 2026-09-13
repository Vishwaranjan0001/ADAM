"""Tests for immutable object storage backend."""

import hashlib
import pytest

from adam.storage.base import (
    ChecksumMismatchError,
    ImmutableObjectOverwriteError,
)
from adam.storage.local import LocalStorageBackend


def test_storage_store_and_retrieve(tmp_storage: LocalStorageBackend):
    data = b"Uttarakhand Government Order Content"
    expected_hash = hashlib.sha256(data).hexdigest()
    key = "orders/2024/go-101.pdf"

    obj = tmp_storage.store(key, data, expected_sha256=expected_hash)
    assert obj.key == key
    assert obj.sha256 == expected_hash
    assert obj.byte_size == len(data)

    retrieved = tmp_storage.get(key)
    assert retrieved == data
    assert tmp_storage.exists(key) is True
    assert tmp_storage.verify_integrity(key, expected_hash) is True


def test_storage_checksum_mismatch_rejected(tmp_storage: LocalStorageBackend):
    data = b"Actual Content"
    wrong_hash = hashlib.sha256(b"Different Content").hexdigest()
    key = "orders/tampered.pdf"

    with pytest.raises(ChecksumMismatchError):
        tmp_storage.store(key, data, expected_sha256=wrong_hash)


def test_storage_idempotent_duplicate_write(tmp_storage: LocalStorageBackend):
    """Writing identical bytes under the same key is a safe, idempotent no-op."""
    data = b"Identical PDF Bytes"
    key = "orders/duplicate.pdf"

    obj1 = tmp_storage.store(key, data)
    obj2 = tmp_storage.store(key, data)

    assert obj1.sha256 == obj2.sha256
    assert tmp_storage.get(key) == data


def test_storage_immutable_overwrite_conflict(tmp_storage: LocalStorageBackend):
    """Writing different bytes under an existing key must be strictly forbidden."""
    key = "orders/original.pdf"
    tmp_storage.store(key, b"Original bytes")

    with pytest.raises(ImmutableObjectOverwriteError):
        tmp_storage.store(key, b"Modified/Tampered bytes")
