"""
stages/notify.py
----------------
Dispatches notifications to all configured notifiers after a pipeline run.

Message content
---------------
Each notifier can define a *title_template* and *message_template* using
simple ``{variable}`` placeholders (rendered via ``str.format_map``).

If *message_template* is blank the stage falls back to an auto-generated
plain-text or HTML message matching the notifier's ``supports_html`` flag.

Available template variables
-----------------------------
  {status}       "succeeded" | "failed"
  {status_emoji} "✅" | "❌"
  {imports}      count of Munki imports
  {failures}     count of recipe failures
  {downloads}    count of URL downloads + pkg copies
  {duration}     e.g. "2m 34s" (empty string if not available)
  {share_url}    raw share-link URL (empty if pwa_base_url not configured)
  {run_id}       UUID string of the run
  {triggered_by} "manual" | "scheduler" | "api"
  {date}         run start date, e.g. "2025-01-15"
  {time}         run start time, e.g. "14:30"

HTML link shorthand (HTML notifiers only)
-----------------------------------------
  {share_link:"Custom Text"}   →  <a href="URL">Custom Text</a>
  {share_link:'Custom Text'}   →  <a href="URL">Custom Text</a>

  When no share URL is configured the placeholder is replaced with an empty
  string so the surrounding sentence stays clean.  Single or double quotes
  are both accepted.
"""

import importlib
import re

from libs.stage import Stage


# -- Template helpers ----------------------------------------------------------

# Matches {share_link:"Custom Text"} and {share_link:'Custom Text'}.
# This syntax is intentionally not valid Python format-string syntax (the colon
# would be misinterpreted as a format-spec separator), so it is handled by a
# dedicated regex pass *before* str.format_map sees the template.
_SHARE_LINK_RE = re.compile(r'\{share_link:(["\'])([^"\']*?)\1\}')


class _SafeDict(dict):
    """dict subclass that returns the raw ``{key}`` placeholder for missing keys."""
    def __missing__(self, key: str) -> str:  # type: ignore[override]
        return '{' + key + '}'


def _render(template: str, ctx: dict) -> str:
    """Render *template* against *ctx*, leaving unknown placeholders intact.

    Handles the HTML link shorthand ``{share_link:"Custom Text"}`` as a
    pre-processing step before the standard ``str.format_map`` call:

    * When a share URL is present: replaced with ``<a href="URL">Custom Text</a>``.
    * When no share URL is configured: replaced with an empty string.
    """
    # -- 1. Handle {share_link:"text"} / {share_link:'text'} ------------------
    share_url = ctx.get('share_url', '')

    def _expand_share_link(m: re.Match) -> str:
        link_text = m.group(2)
        if share_url:
            return f'<a href="{share_url}">{link_text}</a>'
        return ''

    template = _SHARE_LINK_RE.sub(_expand_share_link, template)

    # -- 2. Standard variable substitution ------------------------------------
    try:
        return template.format_map(_SafeDict(ctx))
    except (ValueError, KeyError):
        return template   # malformed format string - return as-is


# -- Stage ---------------------------------------------------------------------

class NotifyOnCompletion(Stage):
    name = "Send notification(s) to user"

    def __init__(self, config, ctx, logger):
        super().__init__(config, ctx, logger)
        self.notifiers: list = config.notifiers
        self.ctx: dict = ctx

    # -- Stage interface -------------------------------------------------------

    def run(self):
        if not self.notifiers:
            self.logger.info("No notifiers configured - skipping.")
            return

        run_id  = self.ctx.get("run_id")
        summary = self._build_summary(run_id)
        tpl_ctx = self._build_template_context(summary, run_id)

        for notifier in self.notifiers:
            ntype = notifier.notifier_type
            self.logger.info(f"Dispatching via notifier '{notifier.name}' ({ntype})")

            module_path = f"notifiers.{ntype}"
            try:
                provider_mod = importlib.import_module(module_path)
            except ModuleNotFoundError:
                self.logger.error(f"Notifier module '{module_path}' not found - skipping.")
                continue

            _send = getattr(provider_mod, "send", None)
            if _send is None:
                self.logger.error(f"Module '{module_path}' has no send() function - skipping.")
                continue

            cfg          = notifier.decrypted_config if hasattr(notifier, 'decrypted_config') else (notifier.config or {})
            # Inject the notifier PK so WebPush can look up its subscriptions.
            cfg = dict(cfg)
            cfg['_notifier_pk'] = str(notifier.pk)
            supports_html = bool(cfg.get("supports_html", False))

            # -- Title ---------------------------------------------------------
            raw_title = getattr(notifier, 'title_template', '') or ''
            title = _render(raw_title, tpl_ctx).strip() if raw_title.strip() else "AutoPkg Runner"

            # -- Message -------------------------------------------------------
            raw_msg = getattr(notifier, 'message_template', '') or ''
            if raw_msg.strip():
                message = _render(raw_msg, tpl_ctx)
                # If the template rendered to nothing (e.g. {share_url} when
                # pwa_base_url is not configured) fall back to the auto-generated
                # message so we never call send() with an empty body.
                if not message.strip():
                    message = self._gen_html_msg(summary) if supports_html else self._gen_plain_msg(summary)
            else:
                message = self._gen_html_msg(summary) if supports_html else self._gen_plain_msg(summary)

            # -- Share URL -----------------------------------------------------
            share_url = tpl_ctx.get("share_url") or None

            try:
                _send(
                    configuration=cfg,
                    message=message,
                    title=title,
                    url=share_url,
                    url_title="View report",
                )
            except Exception:
                self.logger.error(f"Failed to send notification via '{notifier.name}'")

    # -- Summary builders ------------------------------------------------------

    def _build_summary(self, run_id) -> dict:
        """Query the DB for run outcome and recipe result counts."""
        summary = {
            "imports":   0,
            "failures":  0,
            "downloads": 0,
            "share_url": None,
        }
        if run_id is None:
            return summary

        try:
            from webapp.models import RecipeResult
            counts: dict[str, int] = {}
            for row in RecipeResult.objects.filter(run_id=run_id).values("result_type"):
                rt = row["result_type"]
                counts[rt] = counts.get(rt, 0) + 1

            summary["imports"]   = counts.get("munki_import", 0)
            summary["failures"]  = counts.get("failure", 0)
            summary["downloads"] = counts.get("url_downloaded", 0) + counts.get("pkg_copied", 0)

            # Build the share link if a PWA base URL is configured.
            try:
                from webapp.models import Run, RunShareToken, Setting
                pwa_base = Setting.get("notify.pwa_base_url", "").rstrip("/")
                if pwa_base:
                    run = Run.objects.get(id=run_id)
                    token_obj = RunShareToken.get_or_create_for_run(run)
                    summary["share_url"] = f"{pwa_base}/share/{token_obj.token}/"
            except Exception:
                pass

        except Exception:
            pass

        return summary

    def _build_template_context(self, summary: dict, run_id) -> dict:
        """Build the ``{variable}`` substitution dict for message templates."""
        # Infer pipeline success from stage executions - at this point in the
        # pipeline all preceding stages have completed and their status is in DB.
        succeeded = True
        duration_str = ""
        triggered_by = ""
        date_str = ""
        time_str = ""

        if run_id is not None:
            try:
                from webapp.models import Run, StageExecution
                run = Run.objects.get(id=run_id)
                triggered_by = run.triggered_by
                date_str     = run.started_at.strftime("%Y-%m-%d")
                time_str     = run.started_at.strftime("%H:%M")
                if run.started_at and run.completed_at:
                    total = int((run.completed_at - run.started_at).total_seconds())
                    mins, secs = divmod(total, 60)
                    duration_str = f"{mins}m {secs}s" if mins else f"{secs}s"

                # If any stage failed, the overall run is a failure.
                succeeded = not StageExecution.objects.filter(
                    run_id=run_id, status="failed"
                ).exists()
            except Exception:
                pass

        return {
            "status":       "succeeded" if succeeded else "failed",
            "status_emoji": "✅" if succeeded else "❌",
            "imports":      summary["imports"],
            "failures":     summary["failures"],
            "downloads":    summary["downloads"],
            "duration":     duration_str,
            "share_url":    summary.get("share_url") or "",
            "run_id":       str(run_id) if run_id else "",
            "triggered_by": triggered_by,
            "date":         date_str,
            "time":         time_str,
        }

    # -- Default message generators (used when no template is set) -------------

    def _gen_plain_msg(self, summary: dict) -> str:
        parts = ["AutoPkg run complete."]
        if summary["imports"]:
            parts.append(f"{summary['imports']} package(s) imported.")
        if summary["downloads"]:
            parts.append(f"{summary['downloads']} download(s) completed.")
        if summary["failures"]:
            parts.append(f"{summary['failures']} failure(s) encountered.")
        return " ".join(parts)

    def _gen_html_msg(self, summary: dict) -> str:
        lines = ["<b>AutoPkg run complete.</b>"]
        stats = []
        if summary["imports"]:
            stats.append(f"<b>{summary['imports']}</b> package(s) imported")
        if summary["downloads"]:
            stats.append(f"<b>{summary['downloads']}</b> download(s) completed")
        if summary["failures"]:
            stats.append(f"<b>{summary['failures']}</b> failure(s) encountered")
        if stats:
            lines.append(" · ".join(stats))
        return "<br>".join(lines)
