"""Testes para core/cache.py"""

import json
import time

import pytest

from core.cache import cache_key, get, load_cache, put, save_cache


def test_cache_key_format():
    key = cache_key("repo", "src/Foo.java", "abc123")
    assert key == "repo:src/Foo.java:abc123"


def test_put_and_get_roundtrip():
    cache: dict = {}
    put(cache, "repo", "src/Foo.java", "sha1", "content here")
    result = get(cache, "repo", "src/Foo.java", "sha1")
    assert result == "content here"


def test_get_returns_none_for_missing():
    cache: dict = {}
    assert get(cache, "repo", "missing.java", "sha") is None


def test_get_returns_none_for_wrong_sha():
    cache: dict = {}
    put(cache, "repo", "src/Foo.java", "sha1", "content")
    assert get(cache, "repo", "src/Foo.java", "sha2") is None


def test_save_and_load_cache(tmp_path, monkeypatch):
    cache_file = str(tmp_path / ".scanner_cache.json")
    monkeypatch.setattr("core.cache.CACHE_FILE", cache_file)

    cache = {}
    put(cache, "repo", "file.java", "sha", "hello")
    save_cache(cache)

    loaded = load_cache()
    assert get(loaded, "repo", "file.java", "sha") == "hello"


def test_load_cache_returns_empty_on_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("core.cache.CACHE_FILE", str(tmp_path / "nonexistent.json"))
    assert load_cache() == {}


def test_load_cache_returns_empty_on_corrupt_file(tmp_path, monkeypatch):
    cache_file = tmp_path / ".scanner_cache.json"
    cache_file.write_text("not valid json", encoding="utf-8")
    monkeypatch.setattr("core.cache.CACHE_FILE", str(cache_file))
    assert load_cache() == {}
