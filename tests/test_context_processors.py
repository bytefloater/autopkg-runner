"""Tests for webapp.context_processors."""
from __future__ import annotations

import pytest
from unittest.mock import patch
from django.test import RequestFactory


@pytest.fixture
def factory():
    return RequestFactory()


# ---------------------------------------------------------------------------
# nav_tabs
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestNavTabs:
    def test_non_superuser_gets_no_admin_tabs(self, factory, user):
        from webapp.context_processors import nav_tabs
        request = factory.get('/')
        request.user = user
        ctx = nav_tabs(request)
        names = [t['name'] for t in ctx['nav_tabs']]
        assert 'users' not in names

    def test_superuser_gets_admin_tabs(self, factory, superuser):
        from webapp.context_processors import nav_tabs
        request = factory.get('/')
        request.user = superuser
        ctx = nav_tabs(request)
        names = [t['name'] for t in ctx['nav_tabs']]
        assert 'users' in names

    def test_mobile_nav_tabs_excludes_recipes(self, factory, superuser):
        from webapp.context_processors import nav_tabs
        request = factory.get('/')
        request.user = superuser
        ctx = nav_tabs(request)
        mobile_names = [t['name'] for t in ctx['mobile_nav_tabs']]
        assert 'recipes' not in mobile_names

    def test_base_tabs_always_present(self, factory, user):
        from webapp.context_processors import nav_tabs
        request = factory.get('/')
        request.user = user
        ctx = nav_tabs(request)
        names = {t['name'] for t in ctx['nav_tabs']}
        for expected in ('dashboard', 'runs'):
            assert expected in names


# ---------------------------------------------------------------------------
# translation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTranslationContextProcessor:
    def test_injects_translation_proxy(self, factory, user):
        from webapp.context_processors import translation
        from webapp.translations import TranslationProxy
        request = factory.get('/')
        request.user = user
        ctx = translation(request)
        assert isinstance(ctx['t'], TranslationProxy)

    def test_injects_current_language(self, factory, user):
        from webapp.context_processors import translation
        request = factory.get('/')
        request.user = user
        ctx = translation(request)
        assert 'current_language' in ctx

    def test_injects_available_languages(self, factory, user):
        from webapp.context_processors import translation
        request = factory.get('/')
        request.user = user
        ctx = translation(request)
        assert isinstance(ctx['available_languages'], list)

    def test_falls_back_to_en_us_on_setting_exception(self, factory, user):
        from webapp.context_processors import translation
        from webapp.translations import TranslationProxy
        request = factory.get('/')
        request.user = user
        with patch('webapp.models.Setting.get', side_effect=Exception('db error')):
            ctx = translation(request)
        assert isinstance(ctx['t'], TranslationProxy)
        assert ctx['current_language'] == 'en-US'
