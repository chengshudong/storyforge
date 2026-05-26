import pytest

from services.model_router.secret_loader import SecretLoader


def test_mask_long_key():
    masked = SecretLoader.mask("sk-1234567890abcdef")
    assert masked == "sk-************cdef"


def test_mask_short_key():
    masked = SecretLoader.mask("abc")
    assert masked == "***"


def test_mask_four_char_key():
    masked = SecretLoader.mask("abcd")
    assert masked == "****"


def test_load_missing_key():
    val = SecretLoader.load("NONEXISTENT_KEY")
    assert val == ""


def test_validate_no_keys_configured():
    result = SecretLoader.validate()
    assert "DEEPSEEK_API_KEY" in result
    assert "OPENAI_API_KEY" in result
    assert all(isinstance(v, bool) for v in result.values())


def test_default_provider_is_local_when_none_configured():
    assert SecretLoader.default_provider() == "local"


def test_has_any_provider_returns_bool():
    assert isinstance(SecretLoader.has_any_provider(), bool)
