"""Tests for webapp.templatetags.webapp_extras."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock


class TestDurationFilter:
    def _call(self, start, end):
        from webapp.templatetags.webapp_extras import duration
        return duration(start, end)

    def test_none_none_returns_dash(self):
        assert self._call(None, None) == '—'

    def test_start_none_returns_dash(self):
        now = datetime.now(timezone.utc)
        assert self._call(now, None) == '—'

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
        assert self._call(now, now - timedelta(seconds=10)) == '—'


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


class TestLookupFilter:
    def _call(self, d, key):
        from webapp.templatetags.webapp_extras import lookup
        return lookup(d, key)

    def test_present_key_in_regular_dict(self):
        assert self._call({'a': 'b'}, 'a') == 'b'

    def test_missing_key_in_regular_dict_returns_none(self):
        assert self._call({'a': 'b'}, 'z') is None

    def test_non_dict_input_returns_none(self):
        assert self._call('string', 'key') is None
        assert self._call(42, 'key') is None
        assert self._call(None, 'key') is None

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
