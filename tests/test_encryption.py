"""Tests for webapp.encryption."""
from __future__ import annotations

import pytest


class TestEncrypt:
    def test_empty_string_returned_as_is(self):
        from webapp.encryption import encrypt
        assert encrypt('') == ''

    def test_none_returned_as_is(self):
        from webapp.encryption import encrypt
        assert encrypt(None) is None

    def test_plaintext_gets_enc_prefix(self):
        from webapp.encryption import encrypt, ENCRYPTED_PREFIX
        result = encrypt('secret')
        assert result is not None
        assert result.startswith(ENCRYPTED_PREFIX)

    def test_encrypt_then_decrypt_roundtrip(self):
        from webapp.encryption import encrypt, decrypt
        assert decrypt(encrypt('hello world')) == 'hello world'


class TestDecrypt:
    def test_value_without_prefix_returned_unchanged(self):
        from webapp.encryption import decrypt
        assert decrypt('plain-text') == 'plain-text'

    def test_empty_value_returned_as_is(self):
        from webapp.encryption import decrypt
        assert decrypt('') == ''
        assert decrypt(None) is None

    def test_invalid_token_returns_empty_string(self):
        from webapp.encryption import decrypt, ENCRYPTED_PREFIX
        assert decrypt(ENCRYPTED_PREFIX + 'notavalidtoken') == ''


class TestIsEncrypted:
    def test_encrypted_value_returns_true(self):
        from webapp.encryption import encrypt, is_encrypted
        assert is_encrypted(encrypt('secret')) is True

    def test_plain_value_returns_false(self):
        from webapp.encryption import is_encrypted
        assert is_encrypted('plaintext') is False

    def test_empty_returns_false(self):
        from webapp.encryption import is_encrypted
        assert is_encrypted('') is False
        assert is_encrypted(None) is False
