"""
Display a native system notification on the AutoPkg Runner host machine.

Platform support:
  macOS  — osascript  (display notification … with title …)
  Linux  — notify-send
"""
import platform
import subprocess
from typing import Optional


def send(
    configuration: dict,
    message: str,
    title: Optional[str] = None,
    url: Optional[str] = None,
    url_title: Optional[str] = None,
):
    """Display a native OS notification on the server that runs AutoPkg Runner.

    Parameters:
        configuration: {}   — no configuration fields required
        message:   Body text of the notification.
        title:     Notification title (optional; defaults to "AutoPkg Runner").
        url:       Appended as plain text to the message body (optional).
                   Most desktop notification systems cannot render hyperlinks.
        url_title: Ignored (URLs are included as plain text).
    """
    notification_title = title or "AutoPkg Runner"

    body = message
    if url:
        label = url_title or "View report"
        body = f"{message}\n{label}: {url}" if message else f"{label}: {url}"

    system = platform.system()

    if system == "Darwin":
        # osascript strings use double-quoted AppleScript strings; escape
        # backslashes and double-quotes to prevent injection.
        def _esc(s: str) -> str:
            return s.replace("\\", "\\\\").replace('"', '\\"')

        script = (
            f'display notification "{_esc(body)}" '
            f'with title "{_esc(notification_title)}"'
        )
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
        )
        if result.returncode != 0:
            err = result.stderr.decode(errors='replace').strip()
            raise RuntimeError(f"osascript failed (exit {result.returncode}): {err}")

    elif system == "Linux":
        result = subprocess.run(
            ["notify-send", notification_title, body],
            capture_output=True,
        )
        if result.returncode != 0:
            err = result.stderr.decode(errors='replace').strip()
            raise RuntimeError(f"notify-send failed (exit {result.returncode}): {err}")

    else:
        raise RuntimeError(
            f"System notifications are not supported on {system}. "
            "Supported platforms: macOS, Linux."
        )
