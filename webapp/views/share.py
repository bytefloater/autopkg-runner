"""
webapp/views/share.py
---------------------
Unauthenticated share-link view for completed run reports.

The URL /share/<token>/ maps to RunShareView.  The token is a cryptographically
random string stored in RunShareToken - it is the *only* access control.

The rendered page intentionally omits:
  - Log entries (LogEntry records)
  - Stack traces (traceback keys stripped from failure result data)
  - Application navigation (no tab bar / back button)
"""

from datetime import timedelta

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from webapp.translations import load_all_raw
from webapp.views.runs import _get_munki_icon_map, _make_auth_header

# Keys that must never appear in the share report for security.
_STRIPPED_KEYS = frozenset({'traceback', 'Traceback'})


def _sanitise_result_rows(rows: list) -> list:
    """Return rows with traceback fields removed."""
    if not isinstance(rows, list):
        return rows
    cleaned = []
    for row in rows:
        if isinstance(row, dict):
            cleaned.append({k: v for k, v in row.items() if k not in _STRIPPED_KEYS})
        else:
            cleaned.append(row)
    return cleaned


class RunShareView(TemplateView):
    """
    Public (no-login) read-only report for a run identified by its share token.

    Renders a stripped-down, mobile-aware page showing:
      - Run status & metadata
      - Stage list with status icons and durations (no logs)
      - Recipe results without tracebacks
    """

    template_name = 'webapp/share.html'

    def get_context_data(self, **kwargs):
        from webapp.models import RunShareToken, Setting
        ctx = super().get_context_data(**kwargs)

        token_obj = get_object_or_404(RunShareToken, token=self.kwargs['token'])

        # Enforce share-link expiry if configured.
        expiry_days_str = Setting.get('notify.share_link_expiry_days', '').strip()
        if expiry_days_str:
            try:
                expiry_days = int(expiry_days_str)
                if expiry_days > 0:
                    age = timezone.now() - token_obj.created_at
                    if age > timedelta(days=expiry_days):
                        raise Http404('This share link has expired.')
            except ValueError:
                pass  # invalid setting value - treat as no expiry

        run = token_obj.run

        # Stages - status + duration only, no log content.
        stages = list(run.stage_executions.order_by('order'))

        # Build icon map once if the repo URL is configured.
        from webapp.models import Setting
        public_url = Setting.get('repository.public_url', '')
        icon_map = {}
        if public_url:
            auth_header = _make_auth_header(
                Setting.get('repository.public_url_username', ''),
                Setting.get('repository.public_url_password', ''),
            )
            proxy_base = reverse('munki-icon-proxy')
            # Determine catalog from the first munki_import result.
            catalog = 'all'
            for rr in run.recipe_results.filter(result_type='munki_import'):
                if rr.data:
                    cats = rr.data[0].get('catalogs', [])
                    if isinstance(cats, list) and cats:
                        catalog = cats[0]
                    elif isinstance(cats, str) and cats:
                        catalog = cats
                break
            icon_map = _get_munki_icon_map(public_url, catalog, auth_header)

        # Recipe results - strip tracebacks for security.
        results = []
        for rr in run.recipe_results.all():
            data = _sanitise_result_rows(rr.data)
            if rr.result_type == 'munki_import' and icon_map:
                data = [
                    {**row, 'icon_url': f'{proxy_base}?path={icon_map[row["name"]]}' if row.get('name') and icon_map.get(row['name']) else ''}
                    for row in data
                ]
            results.append({
                'result_type': rr.result_type,
                'data':        data,
            })

        from webapp import translations as _trans
        ctx.update({
            'run':              run,
            'stages':           stages,
            'results':          results,
            # Always render the share page in the fallback language — the
            # browser-side language picker handles translation independently.
            't':                _trans.load(_trans.FALLBACK_LANG),
            'all_translations': load_all_raw(),
        })
        return ctx
