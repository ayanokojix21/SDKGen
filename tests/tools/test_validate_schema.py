"""Tests for backend/tools/validate_schema.py."""
import pytest
from backend.tools.validate_schema import validate_schema, _generate_name


def test_validate_schema_valid():
    schema = {
        "api_name": "Test",
        "base_url": "https://api.example.com",
        "auth": {"type": "bearer", "location": "header", "key_name": "Authorization", "example": "token"},
        "endpoints": [
            {"name": "get_users", "path": "/users", "method": "GET", "description": ""},
        ],
    }
    result = validate_schema(schema)
    assert result["valid"] is True
    assert len(result["errors"]) == 0


def test_validate_schema_missing_base_url():
    schema = {
        "api_name": "Test",
        "base_url": "",
        "endpoints": [],
    }
    result = validate_schema(schema)
    assert result["valid"] is False
    assert any("base_url" in e for e in result["errors"])


def test_validate_schema_auto_fixes():
    schema = {
        "api_name": "Test",
        "base_url": "api.example.com/",  # no scheme, trailing slash
        "auth": None,
        "endpoints": [
            {"name": "", "path": "users", "method": "get", "description": ""},  # needs fixes
        ],
    }
    result = validate_schema(schema)
    assert len(result["fixes"]) > 0
    # base_url should have https:// and no trailing slash
    assert result["schema"]["base_url"].startswith("https://")
    assert not result["schema"]["base_url"].endswith("/")
    # method should be uppercased
    assert result["schema"]["endpoints"][0]["method"] == "GET"
    # path should start with /
    assert result["schema"]["endpoints"][0]["path"] == "/users"


def test_validate_schema_invalid_method():
    schema = {
        "api_name": "Test",
        "base_url": "https://api.example.com",
        "endpoints": [
            {"name": "bad", "path": "/bad", "method": "INVALID"},
        ],
    }
    result = validate_schema(schema)
    assert any("Invalid method" in e for e in result["errors"])


def test_validate_schema_not_dict():
    result = validate_schema("not a dict")
    assert result["valid"] is False
    assert "not a dict" in result["errors"][0]


def test_generate_name():
    assert _generate_name("GET", "/users") == "get_users"
    assert _generate_name("POST", "/users") == "create_users"
    assert _generate_name("DELETE", "/users/{id}") == "delete_users_by_id"


def test_validate_schema_auth_normalization():
    schema = {
        "api_name": "Test",
        "base_url": "https://api.example.com",
        "auth": {"type": "bearer_token"},
        "endpoints": [],
    }
    result = validate_schema(schema)
    assert result["schema"]["auth"]["type"] == "bearer"
    assert any("bearer_token" in f for f in result["fixes"])


def test_validate_schema_path_params():
    schema = {
        "api_name": "Test",
        "base_url": "https://api.example.com",
        "endpoints": [
            {"name": "get_user", "path": "/users/{user_id}", "method": "GET", "path_params": []},
        ],
    }
    result = validate_schema(schema)
    # Should auto-add user_id as path param
    ep = result["schema"]["endpoints"][0]
    param_names = [p["name"] for p in ep["path_params"]]
    assert "user_id" in param_names
