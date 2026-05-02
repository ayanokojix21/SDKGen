"""Tests for backend/config.py — Settings validation."""
import os
import pytest


def test_settings_validation_success():
    """Test that validation passes when all required keys are present."""
    from backend.config import Settings
    s = Settings()
    s.GOOGLE_API_KEY = "test_google_key"
    s.MONGODB_URI = "test_mongo_uri"
    s.validate()  # Should not raise


def test_settings_validation_missing_google_key():
    """Test that validation fails when GOOGLE_API_KEY is missing."""
    from backend.config import Settings
    s = Settings()
    s.GOOGLE_API_KEY = ""
    s.MONGODB_URI = "test_mongo_uri"

    with pytest.raises(EnvironmentError) as exc_info:
        s.validate()
    assert "GOOGLE_API_KEY" in str(exc_info.value)


def test_settings_validation_missing_mongo_uri():
    """Test that validation fails when MONGODB_URI is missing."""
    from backend.config import Settings
    s = Settings()
    s.GOOGLE_API_KEY = "test_google_key"
    s.MONGODB_URI = ""

    with pytest.raises(EnvironmentError) as exc_info:
        s.validate()
    assert "MONGODB_URI" in str(exc_info.value)


def test_settings_validation_missing_both():
    """Test that validation fails when both keys are missing."""
    from backend.config import Settings
    s = Settings()
    s.GOOGLE_API_KEY = ""
    s.MONGODB_URI = ""

    with pytest.raises(EnvironmentError) as exc_info:
        s.validate()
    assert "GOOGLE_API_KEY" in str(exc_info.value)
    assert "MONGODB_URI" in str(exc_info.value)


def test_settings_default_values():
    """Test static default values that do not depend on env."""
    from backend.config import Settings
    s = Settings()

    # These are hardcoded defaults, not loaded from .env
    assert s.MAX_ITERATIONS == 15
    assert s.MAX_QA_ROUNDS == 4
    assert s.CHECKPOINT_COLLECTION == "lg_checkpoints"
    assert s.WRITES_COLLECTION == "lg_writes"
    # Port default is 8000 unless overridden
    assert isinstance(s.PORT, int)
