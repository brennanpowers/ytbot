import os
from unittest.mock import patch

import pytest

from bot.config import _clean, _deep_merge, _require


class TestClean:
    def test_none_returns_none(self):
        assert _clean(None) is None

    def test_empty_string_returns_none(self):
        assert _clean("") is None

    def test_whitespace_only_returns_none(self):
        assert _clean("   ") is None

    def test_strips_inline_comment(self):
        assert _clean("value # some comment") == "value"

    def test_strips_whitespace(self):
        assert _clean("  value  ") == "value"

    def test_plain_value(self):
        assert _clean("hello") == "hello"

    def test_hash_at_start_returns_none(self):
        assert _clean("# just a comment") is None

    def test_value_with_multiple_hashes(self):
        assert _clean("value # comment # more") == "value"


class TestDeepMerge:
    def test_flat_override(self):
        base = {"a": 1, "b": 2}
        _deep_merge(base, {"b": 3})
        assert base == {"a": 1, "b": 3}

    def test_adds_new_key(self):
        base = {"a": 1}
        _deep_merge(base, {"b": 2})
        assert base == {"a": 1, "b": 2}

    def test_nested_merge(self):
        base = {"top": {"a": 1, "b": 2}}
        _deep_merge(base, {"top": {"b": 3}})
        assert base == {"top": {"a": 1, "b": 3}}

    def test_deeply_nested_merge(self):
        base = {"a": {"b": {"c": 1, "d": 2}}}
        _deep_merge(base, {"a": {"b": {"d": 3}}})
        assert base == {"a": {"b": {"c": 1, "d": 3}}}

    def test_override_dict_with_scalar(self):
        base = {"a": {"nested": 1}}
        _deep_merge(base, {"a": "flat"})
        assert base == {"a": "flat"}

    def test_override_scalar_with_dict(self):
        base = {"a": "flat"}
        _deep_merge(base, {"a": {"nested": 1}})
        assert base == {"a": {"nested": 1}}

    def test_empty_override_is_noop(self):
        base = {"a": 1}
        _deep_merge(base, {})
        assert base == {"a": 1}


class TestRequire:
    def test_missing_var_exits(self):
        with pytest.raises(SystemExit):
            _require("_YTBOT_TEST_MISSING_VAR_XYZ")

    def test_returns_cleaned_value(self):
        with patch.dict(os.environ, {"_YTBOT_TEST_VAR": "hello # comment"}):
            assert _require("_YTBOT_TEST_VAR") == "hello"
