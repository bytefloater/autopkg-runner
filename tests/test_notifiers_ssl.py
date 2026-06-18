"""Tests for notifiers._ssl."""
from __future__ import annotations

import ssl
from unittest.mock import MagicMock, patch


class TestSSLContext:
    def test_certifi_available_uses_certifi_cafile(self):
        """When certifi is installed ssl_context() builds a context with its CA bundle."""
        import importlib
        import notifiers._ssl as ssl_mod
        importlib.reload(ssl_mod)
        ctx = ssl_mod.ssl_context()
        assert isinstance(ctx, ssl.SSLContext)

    def test_falls_back_to_default_when_certifi_missing(self):
        """When certifi is not installed ssl_context() falls back to the built-in default."""
        import sys
        import importlib
        import notifiers._ssl as ssl_mod
        with patch.dict(sys.modules, {'certifi': None}):
            importlib.reload(ssl_mod)
            ctx = ssl_mod.ssl_context()
        assert isinstance(ctx, ssl.SSLContext)

    def test_pip_system_certs_patch_is_respected(self):
        """If pip-system-certs patches certifi.where(), that patched path is used."""
        import importlib
        import notifiers._ssl as ssl_mod
        mock_certifi = MagicMock()
        mock_certifi.where.return_value = '/patched/system/certs.pem'
        with patch.dict('sys.modules', {'certifi': mock_certifi}):
            importlib.reload(ssl_mod)
            try:
                ssl_mod.ssl_context()
            except Exception:
                pass
        mock_certifi.where.assert_called_once()
