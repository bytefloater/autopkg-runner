"""
Plist-based config loader for the frozen .app bundle.

Reads /Library/Preferences/com.bytefloater.autopkg-runner.plist (system-wide)
or ~/Library/Preferences/com.bytefloater.autopkg-runner.plist (user fallback)
and injects each key as an environment variable before Django initialises.

On first run, if DJANGO_SECRET_KEY is absent it is auto-generated and written
back to the plist so the key is stable across restarts.
"""
import os
import plistlib
import secrets
from pathlib import Path

from __info__ import BUNDLE_ID
_SYSTEM_PLIST = Path(f'/Library/Preferences/{BUNDLE_ID}.plist')
_USER_PLIST = Path.home() / f'Library/Preferences/{BUNDLE_ID}.plist'


def _plist_path() -> Path:
    """Return the plist path to use, preferring system-wide if writable."""
    if _SYSTEM_PLIST.exists() or os.access(_SYSTEM_PLIST.parent, os.W_OK):
        return _SYSTEM_PLIST
    return _USER_PLIST


def load_plist_config() -> None:
    """Read the config plist and inject keys into os.environ.

    Auto-generates and persists DJANGO_SECRET_KEY if not already present.
    """
    path = _plist_path()
    config: dict = {}

    if path.exists():
        with open(path, 'rb') as f:
            config = plistlib.load(f)

    if 'DJANGO_SECRET_KEY' not in config:
        config['DJANGO_SECRET_KEY'] = secrets.token_hex(50)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'wb') as f:
            plistlib.dump(config, f)

    for key, val in config.items():
        os.environ.setdefault(key, str(val))

    # HTTPS redirect is off by default in the bundle — there is no TLS
    # termination unless the user has set up a reverse proxy and explicitly
    # set DJANGO_HTTPS_REDIRECT=true in the preferences plist.
    os.environ.setdefault('DJANGO_HTTPS_REDIRECT', 'false')
