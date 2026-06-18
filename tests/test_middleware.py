"""Tests for webapp.middleware."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestIsReadonlyDbError:
    def _call(self, exc):
        from webapp.middleware import _is_readonly_db_error
        return _is_readonly_db_error(exc)

    def test_non_operational_error_returns_false(self):
        assert self._call(ValueError('nope')) is False
        assert self._call(RuntimeError('nope')) is False

    def test_readonly_message_returns_true(self):
        from django.db.utils import OperationalError
        assert self._call(OperationalError('attempt to write a readonly database')) is True

    def test_non_readonly_operational_error_returns_false(self):
        from django.db.utils import OperationalError
        assert self._call(OperationalError('table not found')) is False


class TestDatabaseWriteGuardMiddleware:
    def _make_middleware(self, get_response):
        from webapp.middleware import DatabaseWriteGuardMiddleware
        return DatabaseWriteGuardMiddleware(get_response)

    def test_passes_through_normal_response(self):
        from django.test import RequestFactory
        from django.http import HttpResponse
        request = RequestFactory().get('/')
        get_response = MagicMock(return_value=HttpResponse('ok'))
        mw = self._make_middleware(get_response)
        resp = mw(request)
        assert resp.status_code == 200

    def test_returns_503_on_readonly_db_error(self):
        from django.test import RequestFactory
        from django.db.utils import OperationalError
        request = RequestFactory().get('/')
        get_response = MagicMock(side_effect=OperationalError('attempt to write a readonly database'))
        mw = self._make_middleware(get_response)
        resp = mw(request)
        assert resp.status_code == 503
        assert b'Database' in resp.content

    def test_reraises_non_readonly_db_error(self):
        from django.test import RequestFactory
        from django.db.utils import OperationalError
        request = RequestFactory().get('/')
        get_response = MagicMock(side_effect=OperationalError('table not found'))
        mw = self._make_middleware(get_response)
        with pytest.raises(OperationalError):
            mw(request)


class TestRemoveServerHeaderMiddleware:
    def test_removes_server_header(self):
        from django.test import RequestFactory
        from django.http import HttpResponse
        from webapp.middleware import RemoveServerHeaderMiddleware
        request = RequestFactory().get('/')
        resp = HttpResponse('ok')
        resp['Server'] = 'gunicorn/20'
        mw = RemoveServerHeaderMiddleware(lambda r: resp)
        result = mw(request)
        assert 'Server' not in result


class TestMobileDetectionMiddleware:
    def _make_middleware(self, get_response=None):
        from webapp.middleware import MobileDetectionMiddleware
        if get_response is None:
            from django.http import HttpResponse
            get_response = lambda r: HttpResponse('ok')
        return MobileDetectionMiddleware(get_response)

    def test_desktop_ua_not_mobile(self):
        from django.test import RequestFactory
        request = RequestFactory().get('/', HTTP_USER_AGENT='Mozilla/5.0 (Macintosh; Intel Mac OS X)')
        mw = self._make_middleware()
        mw(request)
        assert request.is_mobile is False

    def test_iphone_ua_is_mobile(self):
        from django.test import RequestFactory
        request = RequestFactory().get('/', HTTP_USER_AGENT='Mozilla/5.0 (iPhone; CPU iPhone OS 16_0)')
        mw = self._make_middleware()
        mw(request)
        assert request.is_mobile is True

    def test_android_ua_is_mobile(self):
        from django.test import RequestFactory
        request = RequestFactory().get('/', HTTP_USER_AGENT='Mozilla/5.0 (Linux; Android 12)')
        mw = self._make_middleware()
        mw(request)
        assert request.is_mobile is True

    def test_desktop_cookie_overrides_mobile_ua(self):
        from django.test import RequestFactory
        request = RequestFactory().get('/', HTTP_USER_AGENT='Mozilla/5.0 (iPhone; CPU iPhone OS 16_0)')
        request.COOKIES = {'desktop_mode': '1'}
        mw = self._make_middleware()
        mw(request)
        assert request.is_mobile is False

    def test_ipad_cookie_triggers_mobile(self):
        from django.test import RequestFactory
        request = RequestFactory().get('/', HTTP_USER_AGENT='Mozilla/5.0 (Macintosh)')
        request.COOKIES = {'ipad_detected': '1'}
        mw = self._make_middleware()
        mw(request)
        assert request.is_mobile is True

    def test_desktop_query_param_sets_cookie(self):
        from django.test import RequestFactory
        from django.http import HttpResponse
        request = RequestFactory().get('/?desktop=1', HTTP_USER_AGENT='Mozilla/5.0 (iPhone)')
        request.COOKIES = {}
        mw = self._make_middleware(lambda r: HttpResponse('ok'))
        resp = mw(request)
        assert 'desktop_mode' in resp.cookies

    def test_mobile_query_param_sets_cookie(self):
        from django.test import RequestFactory
        from django.http import HttpResponse
        request = RequestFactory().get('/?mobile=1', HTTP_USER_AGENT='Mozilla/5.0 (Macintosh)')
        request.COOKIES = {}
        mw = self._make_middleware(lambda r: HttpResponse('ok'))
        resp = mw(request)
        assert 'ipad_detected' in resp.cookies
