import importlib
from libs.stage import Stage


class NotifyOnCompletion(Stage):
    name = "Send notification(s) to user"

    def __init__(self, config, ctx, logger):
        super().__init__(config, ctx, logger)

        self.notify_settings: dict  = config.module_settings.notify
        self.providers: list        = self.notify_settings["providers"]
        self.ctx: dict              = ctx

    def run(self):
        for provider in self.providers:
            module = f"notifiers.{provider}"
            self.logger.info(f"Looking for module: {module}")
            try:
                provider_mod = importlib.import_module(module)
            except ModuleNotFoundError:
                self.logger.error(f"Module '{module}' not found!")
                continue

            # Grab its `send(token, user, message, title)` function
            _send = getattr(provider_mod, "send")
            provider_config = self.notify_settings.get(module, {})
            supports_html = provider_config.get("supports_html", False)

            try:
                self.logger.info(f"Sending notification with provider: {module}")
                _send(
                    configuration=provider_config,
                    message=self._generate_message(supports_html)
                )
            except Exception as err:
                self.logger.error("Failed to send notification")
        
    def _generate_message(self, supports_html) -> str:
        if supports_html:
            return self._gen_html_msg()
        return self._gen_non_html_msg()

    def _gen_non_html_msg(self) -> str:
        report_url: str = self.ctx.get("stage_outputs", {}).get("GenerateReport")
        message = f"""AutoPkg run complete, a new report is available from {report_url}"""
        return message

    def _gen_html_msg(self) -> str:
        report_url: str = self.ctx.get("stage_outputs", {}).get("GenerateReport")
        message = f"""AutoPkg run complete, a new report is available <a href="{report_url}">here</a>"""
        return message