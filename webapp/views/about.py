"""
webapp/views/about.py
─────────────────────
About page - shows application version, AutoPkg version (with update check),
and MunkiTools version.

All external calls (subprocess + GitHub API) are wrapped in try/except so the
page always renders even if autopkg is not installed or the network is down.
"""
from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from typing import Optional

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


def _run(*args: str, timeout: int = 5) -> str:
    """Run a command and return stdout, or empty string on any error."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()
    except Exception:
        return ''


def _autopkg_version(bin_path: str) -> Optional[str]:
    """Return the installed AutoPkg version string, or None if not found."""
    out = _run(bin_path, 'version')
    return out or None


def _autopkg_latest_release() -> Optional[str]:
    """Fetch the latest AutoPkg release tag from GitHub. Returns None on failure."""
    url = 'https://api.github.com/repos/autopkg/autopkg/releases/latest'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'autopkg-runner/3.0.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            tag = data.get('tag_name', '')
            # Tags are typically 'v2.7.2' - strip leading 'v'
            return tag.lstrip('v') or None
    except Exception:
        return None


def _munki_version() -> Optional[str]:
    """Return the installed MunkiTools version, or None if not found."""
    # Try managedsoftwareupdate first (most reliable version source)
    for candidate in (
        '/usr/local/munki/managedsoftwareupdate',
        '/usr/local/munki/munki-run',
    ):
        out = _run(candidate, '--version')
        if out:
            return out

    # Fallback: read the version from the Munki receipt plist
    plist_path = '/Library/Managed Installs/ManagedInstallReport.plist'
    try:
        import pathlib
        import plistlib
        data = plistlib.loads(pathlib.Path(plist_path).read_bytes())
        v = data.get('ManagedInstallVersion', '')
        return v or None
    except Exception:
        pass

    return None


def _parse_version(v: str) -> tuple:
    """Parse a dotted version string into a comparable tuple of ints."""
    try:
        return tuple(int(x) for x in v.split('.') if x.isdigit())
    except Exception:
        return (0,)


class AboutView(LoginRequiredMixin, TemplateView):
    template_name = 'webapp/about.html'

    def get_template_names(self):
        if getattr(self.request, 'is_mobile', False):
            return ['webapp/mobile/about.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        from webapp.models import Setting
        from __info__ import APP_VERSION_STR, FRIENDLY_APP_NAME

        ctx = super().get_context_data(**kwargs)
        ctx['active_tab'] = 'config'

        ctx['app_name']    = FRIENDLY_APP_NAME
        ctx['app_version'] = APP_VERSION_STR

        # ── AutoPkg ───────────────────────────────────────────────────────────
        autopkg_bin    = Setting.get('autopkg.bin_path', '/usr/local/bin/autopkg')
        autopkg_ver    = _autopkg_version(autopkg_bin)
        autopkg_latest = _autopkg_latest_release() if autopkg_ver else None

        ctx['autopkg_version']      = autopkg_ver        # None = not installed
        ctx['autopkg_latest']       = autopkg_latest     # None = couldn't check
        ctx['autopkg_update_available'] = (
            autopkg_ver and autopkg_latest
            and _parse_version(autopkg_latest) > _parse_version(autopkg_ver)
        )

        # ── MunkiTools ────────────────────────────────────────────────────────
        ctx['munki_version'] = _munki_version()          # None = not installed

        return ctx
