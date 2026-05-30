"""
webapp/views/share.py
─────────────────────
Unauthenticated share-link view for completed run reports.

The URL /share/<token>/ maps to RunShareView.  The token is a cryptographically
random string stored in RunShareToken — it is the *only* access control.

The rendered page intentionally omits:
  - Log entries (LogEntry records)
  - Stack traces (traceback keys stripped from failure result data)
  - Application navigation (no tab bar / back button)
"""

from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView

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
        from webapp.models import RunShareToken
        ctx = super().get_context_data(**kwargs)

        token_obj = get_object_or_404(RunShareToken, token=self.kwargs['token'])
        run       = token_obj.run

        # Stages — status + duration only, no log content.
        stages = list(run.stage_executions.order_by('order'))

        # Recipe results — strip tracebacks for security.
        results = []
        for rr in run.recipe_results.all():
            results.append({
                'result_type': rr.result_type,
                'data':        _sanitise_result_rows(rr.data),
            })

        ctx.update({
            'run':     run,
            'stages':  stages,
            'results': results,
        })
        return ctx
