"""Tests for webapp.templatetags.webapp_extras."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock


class TestDurationFilter:
    def _call(self, start, end):
        from webapp.templatetags.webapp_extras import duration
        return duration(start, end)

    def test_none_none_returns_dash(self):
        assert self._call(None, None) == '-'

    def test_start_none_returns_dash(self):
        now = datetime.now(timezone.utc)
        assert self._call(now, None) == '-'

    def test_45_seconds(self):
        now = datetime.now(timezone.utc)
        assert self._call(now - timedelta(seconds=45), now) == '45s'

    def test_90_seconds(self):
        now = datetime.now(timezone.utc)
        assert self._call(now - timedelta(seconds=90), now) == '1m 30s'

    def test_3750_seconds(self):
        now = datetime.now(timezone.utc)
        assert self._call(now - timedelta(seconds=3750), now) == '1h 2m'

    def test_exactly_60_seconds(self):
        now = datetime.now(timezone.utc)
        assert self._call(now - timedelta(seconds=60), now) == '1m 0s'

    def test_negative_delta_returns_dash(self):
        now = datetime.now(timezone.utc)
        # end before start
        assert self._call(now, now - timedelta(seconds=10)) == '-'


class TestStatusColorFilter:
    def _call(self, status):
        from webapp.templatetags.webapp_extras import status_color
        return status_color(status)

    def test_known_statuses_return_nonempty_string(self):
        for s in ('pending', 'running', 'success', 'failed', 'cancelled', 'skipped'):
            result = self._call(s)
            assert isinstance(result, str) and result

    def test_unknown_status_returns_fallback_string(self):
        result = self._call('unknown_xyz')
        assert isinstance(result, str) and result


class TestLevelColorFilter:
    def _call(self, level):
        from webapp.templatetags.webapp_extras import level_color
        return level_color(level)

    def test_known_levels_return_nonempty_string(self):
        for lvl in ('DEBUG', 'INFO', 'NOTICE', 'WARNING', 'ERROR', 'CRITICAL'):
            result = self._call(lvl)
            assert isinstance(result, str) and result

    def test_unknown_level_returns_fallback(self):
        assert self._call('VERBOSE') == 'text-gray-600'


class TestLookupFilter:
    def _call(self, d, key):
        from webapp.templatetags.webapp_extras import lookup
        return lookup(d, key)

    def test_present_key_in_regular_dict(self):
        assert self._call({'a': 'b'}, 'a') == 'b'

    def test_missing_key_in_regular_dict_returns_empty_string(self):
        assert self._call({'a': 'b'}, 'z') == ''

    def test_non_dict_input_returns_empty_string(self):
        assert self._call('string', 'key') == ''
        assert self._call(42, 'key') == ''
        assert self._call(None, 'key') == ''

    def test_missing_key_in_translation_proxy_returns_dotted_path(self):
        from webapp.translations import TranslationProxy
        proxy = TranslationProxy({'APP': {'NAME': 'AutoPkg Runner'}}, '')
        result = self._call(proxy['APP'], 'MISSING_KEY')
        assert str(result) == 'APP.MISSING_KEY'

    def test_present_key_in_translation_proxy_returns_value(self):
        from webapp.translations import TranslationProxy
        proxy = TranslationProxy({'APP': {'NAME': 'AutoPkg Runner'}}, '')
        result = self._call(proxy['APP'], 'NAME')
        assert result == 'AutoPkg Runner'


class TestLucideTag:
    def test_missing_icon_returns_span_fallback(self):
        from webapp.templatetags.webapp_extras import lucide, _SVG_CACHE
        # Ensure 'nonexistent-icon' is not in cache
        _SVG_CACHE.pop('nonexistent-icon', None)
        with patch('django.contrib.staticfiles.finders.find', return_value=None):
            result = lucide('nonexistent-icon', 'w-5 h-5')
        assert '<span' in result
        assert 'w-5 h-5' in result

    def test_present_icon_returns_svg_with_classes(self):
        from webapp.templatetags.webapp_extras import lucide, _SVG_CACHE
        _SVG_CACHE.pop('test-icon', None)
        fake_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><path d="M0 0"/></svg>'
        with patch('django.contrib.staticfiles.finders.find', return_value='/fake/path.svg'), \
             patch('builtins.open', MagicMock(return_value=MagicMock(
                 __enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value=fake_svg))),
                 __exit__=MagicMock(return_value=False),
             ))):
            result = lucide('test-icon', 'w-4 h-4')
        assert '<svg' in result
        assert 'w-4 h-4' in result
        assert 'width=' not in result
        assert 'height=' not in result

    def test_license_comment_stripped(self):
        from webapp.templatetags.webapp_extras import lucide, _SVG_CACHE
        _SVG_CACHE.pop('comment-icon', None)
        fake_svg = '<!-- @license MIT -->\n<svg xmlns="http://www.w3.org/2000/svg"><path d=""/></svg>'
        with patch('django.contrib.staticfiles.finders.find', return_value='/fake/path.svg'), \
             patch('builtins.open', MagicMock(return_value=MagicMock(
                 __enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value=fake_svg))),
                 __exit__=MagicMock(return_value=False),
             ))):
            result = lucide('comment-icon', 'w-5 h-5')
        assert '<!--' not in result
        assert '@license' not in result


class TestEnsureListFilter:
    def _call(self, val):
        from webapp.templatetags.webapp_extras import ensure_list
        return ensure_list(val)

    def test_list_returned_as_is(self):
        assert self._call(['a', 'b']) == ['a', 'b']

    def test_non_list_truthy_value_wrapped(self):
        assert self._call('single') == ['single']

    def test_falsy_value_returns_empty_list(self):
        assert self._call('') == []
        assert self._call(None) == []
        assert self._call(0) == []


class TestJsonEncodeFilter:
    def _call(self, val):
        from webapp.templatetags.webapp_extras import json_encode
        return json_encode(val)

    def test_dict_encoded_to_json(self):
        result = str(self._call({'name': 'App', 'version': '1.0'}))
        assert 'App' in result
        assert '1.0' in result

    def test_double_quotes_escaped_for_html_attribute(self):
        result = str(self._call({'key': 'val'}))
        assert '"' not in result

    def test_non_serialisable_uses_str_fallback(self):
        from datetime import datetime
        result = str(self._call({'ts': datetime(2024, 1, 1)}))
        assert '2024' in result


class TestResultTypeLabelFilter:
    def _t(self):
        from webapp.translations import load
        return load('en-US')

    def test_known_result_type_returns_translation(self):
        from webapp.templatetags.webapp_extras import result_type_label
        result = result_type_label('failure', self._t())
        assert result == 'Failures'

    def test_munki_import_returns_translation(self):
        from webapp.templatetags.webapp_extras import result_type_label
        result = result_type_label('munki_import', self._t())
        assert isinstance(result, str) and result

    def test_unknown_result_type_returns_synthetic_key(self):
        from webapp.templatetags.webapp_extras import result_type_label
        result = result_type_label('custom_type', self._t())
        assert 'CUSTOM_TYPE' in result

    def test_none_t_returns_synthetic_key(self):
        from webapp.templatetags.webapp_extras import result_type_label
        result = result_type_label('failure', None)
        assert 'FAILURE' in result

    def test_plain_dict_missing_key_returns_dotted_fallback(self):
        from webapp.templatetags.webapp_extras import result_type_label
        # Truthy dict without RUN_DETAIL_VIEW triggers the except (KeyError) branch
        result = result_type_label('failure', {'other': 'data'})
        assert 'RUN_DETAIL_VIEW' in result


class TestResultFieldLabelTag:
    def _t(self):
        from webapp.translations import load
        return load('en-US')

    def test_known_field_returns_translation(self):
        from webapp.templatetags.webapp_extras import result_field_label
        result = result_field_label('message', 'failure', self._t())
        assert result == 'Message'

    def test_result_type_qualified_lookup_wins(self):
        from webapp.templatetags.webapp_extras import result_field_label
        result = result_field_label('name', 'deprecation', self._t())
        assert isinstance(result, str) and result

    def test_unknown_field_returns_synthetic_key(self):
        from webapp.templatetags.webapp_extras import result_field_label
        result = result_field_label('exotic_field', 'failure', self._t())
        assert 'EXOTIC_FIELD' in result

    def test_plain_dict_missing_key_returns_dotted_fallback(self):
        from webapp.templatetags.webapp_extras import result_field_label
        # Truthy dict without RUN_DETAIL_VIEW triggers the except (KeyError) branch
        result = result_field_label('message', 'failure', {'other': 'data'})
        assert 'RUN_DETAIL_VIEW' in result


class TestLookupFilterNoneValue:
    def test_none_value_returns_empty_string(self):
        from webapp.templatetags.webapp_extras import lookup
        assert lookup({'key': None}, 'key') == ''
