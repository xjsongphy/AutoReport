"""Tests for provider preset parsing."""

from pathlib import Path

from autoreport.config.presets import (
    ProviderPreset,
    _builtin_presets,
    _extract_ts_number,
    _extract_ts_string,
    _parse_claude_presets,
    _split_ts_objects,
    _strip_ts_comments,
    get_presets_by_category,
    load_presets,
)


def test_strip_ts_comments_line():
    src = 'const x = "hello"; // this is a comment'
    result = _strip_ts_comments(src)
    assert "// this is a comment" not in result
    assert '"hello"' in result


def test_strip_ts_comments_block():
    src = 'const x = /* inline */ "hello";'
    result = _strip_ts_comments(src)
    assert "/* inline */" not in result
    assert '"hello"' in result


def test_extract_ts_string_double_quotes():
    ts = 'name: "Anthropic (Official)"'
    assert _extract_ts_string(ts, "name") == "Anthropic (Official)"


def test_extract_ts_string_single_quotes():
    ts = "name: 'DeepSeek'"
    assert _extract_ts_string(ts, "name") == "DeepSeek"


def test_extract_ts_string_missing():
    assert _extract_ts_string("no key here", "name") is None


def test_extract_ts_number():
    ts = "timeout: 300"
    assert _extract_ts_number(ts, "timeout") == 300


def test_extract_ts_number_missing():
    assert _extract_ts_number("no number", "timeout") is None


def test_split_ts_objects():
    text = '{ a: 1 } { b: "hello" }'
    objects = _split_ts_objects(text)
    assert len(objects) == 2
    assert "a: 1" in objects[0]
    assert '"hello"' in objects[1]


def test_split_ts_objects_nested():
    text = '{ a: { nested: true } } { b: 2 }'
    objects = _split_ts_objects(text)
    assert len(objects) == 2


def test_split_ts_objects_with_strings_containing_braces():
    text = '{ url: "http://example.com/{id}" } { b: 2 }'
    objects = _split_ts_objects(text)
    assert len(objects) == 2


def test_parse_claude_presets_missing_file():
    result = _parse_claude_presets(Path("/nonexistent/file.ts"))
    assert result == []


def test_parse_claude_presets_basic():
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    try:
        ts_content = """
export const providerPresets: ProviderPreset[] = [
  {
    name: "Test Provider",
    category: "official",
    settingsConfig: {
      env: {
        ANTHROPIC_BASE_URL: "https://api.test.com",
        ANTHROPIC_MODEL: "test-model",
      }
    },
    websiteUrl: "https://test.com",
    apiKeyUrl: "https://test.com/keys",
    iconColor: "#FF0000",
  }
];
"""
        ts_file = tmp / "test_presets.ts"
        ts_file.write_text(ts_content, encoding="utf-8")

        presets = _parse_claude_presets(ts_file)
        assert len(presets) == 1
        assert presets[0].name == "Test Provider"
        assert presets[0].provider == "anthropic"
        assert presets[0].base_url == "https://api.test.com"
        assert presets[0].default_model == "test-model"
        assert presets[0].category == "official"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_builtin_presets():
    presets = _builtin_presets()
    assert len(presets) >= 6

    providers = {p.provider for p in presets}
    assert "anthropic" in providers
    assert "openai" in providers
    assert "deepseek" in providers
    assert "custom" in providers


def test_builtin_presets_structure():
    presets = _builtin_presets()
    for p in presets:
        assert p.name
        assert p.provider
        assert p.category


def test_load_presets_returns_builtin():
    presets = load_presets()
    assert len(presets) >= 6

    providers = {p.provider for p in presets}
    assert "anthropic" in providers


def test_load_presets_no_duplicates():
    presets = load_presets()
    names = [p.name.lower() for p in presets]
    assert len(names) == len(set(names))


def test_get_presets_by_category():
    groups = get_presets_by_category()
    assert isinstance(groups, dict)
    assert "official" in groups
    assert "custom" in groups
    for cat, presets in groups.items():
        for p in presets:
            assert p.category == cat or (cat == "custom" and p.category == "custom")


def test_provider_preset_dataclass():
    p = ProviderPreset(
        name="Test",
        provider="openai",
        category="official",
        base_url="https://api.test.com",
    )
    assert p.name == "Test"
    assert p.api_key_url is None
    assert p.description == ""
