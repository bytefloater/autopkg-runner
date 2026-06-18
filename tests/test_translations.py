"""Tests for webapp.translations: TranslationProxy, load(), available()."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch


class TestTranslationProxy:
    def _make_proxy(self, data: dict, path: str = ''):
        from webapp.translations import TranslationProxy
        return TranslationProxy(data, path)

    def test_present_key_returns_value(self):
        p = self._make_proxy({'FOO': 'bar'})
        assert p['FOO'] == 'bar'

    def test_missing_key_returns_proxy_with_dotted_path(self):
        p = self._make_proxy({}, 'SECTION')
        result = p['MISSING']
        assert str(result) == 'SECTION.MISSING'

    def test_empty_string_value_omitted_missing_returns_dotted_path(self):
        p = self._make_proxy({'EMPTY': ''}, 'SEC')
        result = p['EMPTY']
        assert str(result) == 'SEC.EMPTY'

    def test_nested_missing_key_accumulates_path(self):
        from webapp.translations import TranslationProxy
        p = TranslationProxy({'A': {}}, '')
        # A exists as a proxy, B is missing
        result = p['A']['B']['C']
        assert str(result) == 'A.B.C'

    def test_deeply_nested_present_key(self):
        from webapp.translations import TranslationProxy
        p = TranslationProxy({'APP': {'NAME': 'AutoPkg Runner'}})
        assert p['APP']['NAME'] == 'AutoPkg Runner'

    def test_str_of_present_proxy_returns_path(self):
        from webapp.translations import TranslationProxy
        p = TranslationProxy({}, 'MY.PATH')
        assert str(p) == 'MY.PATH'

    def test_format_delegates_to_path(self):
        from webapp.translations import TranslationProxy
        p = TranslationProxy({}, 'X.Y')
        assert f'{p}' == 'X.Y'


class TestLoad:
    def test_load_en_us_returns_proxy(self):
        from webapp.translations import load, TranslationProxy
        # Clear cache so our module-level lru_cache doesn't interfere
        load.cache_clear()
        result = load('en-US')
        assert isinstance(result, TranslationProxy)

    def test_load_known_key(self):
        from webapp.translations import load
        load.cache_clear()
        t = load('en-US')
        assert str(t['APP']['NAME']) == 'AutoPkg Runner'

    def test_load_cached_returns_same_object(self):
        from webapp.translations import load
        load.cache_clear()
        t1 = load('en-US')
        t2 = load('en-US')
        assert t1 is t2

    def test_load_falls_back_to_en_us_for_unknown_lang(self):
        from webapp.translations import load, TranslationProxy
        load.cache_clear()
        result = load('xx-FAKE')
        assert isinstance(result, TranslationProxy)
        # Should have fallen back to en-US content
        assert str(result['APP']['NAME']) == 'AutoPkg Runner'
        load.cache_clear()

    def test_at_reference_resolved(self):
        """@: pointer in JSON is replaced with the pointed-to value."""
        from webapp.translations import _resolve_all
        raw = {'FOO': 'hello', 'BAR': '@:FOO'}
        resolved = _resolve_all(raw, raw)
        assert resolved['BAR'] == 'hello'

    def test_at_reference_broken_ref_returns_as_is(self):
        from webapp.translations import _resolve_all
        raw = {'BAR': '@:NONEXISTENT'}
        resolved = _resolve_all(raw, raw)
        assert resolved['BAR'] == '@:NONEXISTENT'


class TestAvailable:
    def test_returns_list_of_tuples(self):
        from webapp.translations import available
        result = available()
        assert isinstance(result, list)
        for item in result:
            assert len(item) == 2

    def test_en_us_is_present(self):
        from webapp.translations import available
        codes = [code for code, _ in available()]
        assert 'en-US' in codes

    def test_sorted_by_code(self):
        from webapp.translations import available
        result = available()
        codes = [code for code, _ in result]
        assert codes == sorted(codes)

    def test_silently_skips_malformed_json(self, tmp_path, monkeypatch):
        from webapp import translations
        load_cache_clear = translations.load.cache_clear
        # Point TRANSLATIONS_DIR at a temp dir with one valid and one bad file
        valid = tmp_path / 'en-US.json'
        valid.write_text(json.dumps({'NAME': 'English'}))
        bad = tmp_path / 'zz-BAD.json'
        bad.write_text('{ not valid json }}}')
        monkeypatch.setattr(translations, 'TRANSLATIONS_DIR', tmp_path)
        result = translations.available()
        codes = [c for c, _ in result]
        assert 'en-US' in codes
        assert 'zz-BAD' not in codes


class TestLoadAllRaw:
    def test_load_all_raw_returns_dict(self):
        from webapp.translations import load_all_raw
        result = load_all_raw()
        assert isinstance(result, dict)
        assert 'en-US' in result

    def test_load_all_raw_skips_bad_json(self, tmp_path, monkeypatch):
        from webapp import translations
        valid = tmp_path / 'en-US.json'
        import json
        valid.write_text(json.dumps({'NAME': 'English'}))
        bad = tmp_path / 'zz-BAD.json'
        bad.write_text('{{bad json}}')
        monkeypatch.setattr(translations, 'TRANSLATIONS_DIR', tmp_path)
        result = translations.load_all_raw()
        assert 'en-US' in result
        assert 'zz-BAD' not in result


class TestResolveRefBrokenAtReference:
    def test_broken_ref_non_dict_part_returns_as_is(self):
        """When traversing @: path hits a non-dict node, returns the original value."""
        from webapp.translations import _resolve_ref
        root = {'FOO': 'string_value'}
        # '@:FOO.BAR' → FOO is 'string_value' (not a dict), so returns '@:FOO.BAR'
        result = _resolve_ref('@:FOO.BAR', root)
        assert result == '@:FOO.BAR'
