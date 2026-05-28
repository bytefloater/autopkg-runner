import importlib

from libs.stage import Stage


class NotifyOnCompletion(Stage):
    name = "Send notification(s) to user"

    def __init__(self, config, ctx, logger):
        super().__init__(config, ctx, logger)
        # config.notifiers is a list of webapp.models.Notifier instances
        self.notifiers: list = config.notifiers
        self.ctx: dict = ctx

    def run(self):
        if not self.notifiers:
            self.logger.info("No notifiers configured — skipping.")
            return

        for notifier in self.notifiers:
            ntype = notifier.notifier_type
            module_path = f"notifiers.{ntype}"
            self.logger.info(f"Dispatching via notifier '{notifier.name}' ({ntype})")

            try:
                provider_mod = importlib.import_module(module_path)
            except ModuleNotFoundError:
                self.logger.error(f"Notifier module '{module_path}' not found — skipping.")
                continue

            _send = getattr(provider_mod, "send", None)
            if _send is None:
                self.logger.error(f"Module '{module_path}' has no send() function — skipping.")
                continue

            cfg = notifier.decrypted_config if hasattr(notifier, 'decrypted_config') else (notifier.config or {})
            supports_html = bool(cfg.get("supports_html", False))

            try:
                _send(
                    configuration=cfg,
                    message=self._generate_message(supports_html),
                    title="AutoPkg Runner",
                )
            except Exception:
                self.logger.error(f"Failed to send notification via '{notifier.name}'")

    # ── Message generation ────────────────────────────────────────────────────

    def _generate_message(self, supports_html: bool) -> str:
        run_id = self.ctx.get("run_id")
        summary = self._build_summary(run_id)
        if supports_html:
            return self._gen_html_msg(summary)
        return self._gen_plain_msg(summary)

    def _build_summary(self, run_id) -> dict:
        """Query DB for run outcome and recipe result counts."""
        summary = {
            "imports": 0,
            "failures": 0,
            "downloads": 0,
            "run_url": None,
        }
        if run_id is None:
            return summary

        try:
            from webapp.models import RecipeResult, Run
            counts = {}
            for row in RecipeResult.objects.filter(run_id=run_id).values("result_type"):
                rt = row["result_type"]
                counts[rt] = counts.get(rt, 0) + 1

            summary["imports"]   = counts.get("munki_import", 0)
            summary["failures"]  = counts.get("failure", 0)
            summary["downloads"] = counts.get("url_downloaded", 0) + counts.get("pkg_copied", 0)

            # Build a link to the run detail page if a public URL is configured
            try:
                from webapp.models import Setting
                public_url = Setting.get("repository.public_url", "").rstrip("/")
                if public_url:
                    summary["run_url"] = f"{public_url}/runs/{run_id}/"
            except Exception:
                pass

        except Exception:
            pass

        return summary

    def _gen_plain_msg(self, summary: dict) -> str:
        parts = ["AutoPkg run complete."]
        if summary["imports"]:
            parts.append(f"{summary['imports']} package(s) imported.")
        if summary["downloads"]:
            parts.append(f"{summary['downloads']} download(s) completed.")
        if summary["failures"]:
            parts.append(f"{summary['failures']} failure(s) encountered.")
        if summary["run_url"]:
            parts.append(f"Details: {summary['run_url']}")
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
        if summary["run_url"]:
            lines.append(f'<a href="{summary["run_url"]}">View run details</a>')
        return "<br>".join(lines)
