"""
A helper module for sending notifications to Pushover
"""
import http.client
from typing import Optional
from urllib.parse import urlencode

from notifiers._ssl import ssl_context


def send(
    configuration: dict,
    message: str,
    title: Optional[str] = None,
    url: Optional[str] = None,
    url_title: Optional[str] = None,
):
    """Send a Pushover notification.

    Parameters:
        configuration: {'app_token': str, 'user_token': str}
        message:   Body content of notification.
        title:     Notification title (optional).
        url:       Supplementary URL shown below the message (optional).
                   Pushover opens this URL when the notification is tapped —
                   use a share link so the in-app browser opens the report.
        url_title: Display label for *url* (optional; defaults to "View report").
    """
    conn = http.client.HTTPSConnection("api.pushover.net", 443)
    conn = http.client.HTTPSConnection("api.pushover.net", 443, context=ssl_context())
    parameters = {
        "token":     configuration["app_token"],
        "user":      configuration["user_token"],
        "title":     title,
        "message":   message,
        "html":      1,
        "ttl":       2592000,   # 30 days
        "url":       url,
        "url_title": url_title or ("View report" if url else None),
    }

    # Strip None values before sending
    parameters = {k: v for k, v in parameters.items() if v is not None}

    conn.request(
        "POST", "/1/messages.json",
        urlencode(parameters),
        {"Content-type": "application/x-www-form-urlencoded"},
    )
    resp = conn.getresponse()
    if resp.status not in (200, 201):
        body = resp.read().decode(errors='replace')
        raise RuntimeError(f"Pushover returned HTTP {resp.status}: {body}")

if __name__ == "__main__":
    import json
    from __info__ import CONFIG_FILE

    with open(CONFIG_FILE, mode="r", encoding="utf-8") as config_file:
        raw = json.load(config_file)

    settings: dict = raw["module_settings"]["core.notify"]["notifiers.pushover"]

    config = {
        "app_token": settings.get("app_token"),
        "user_token": settings.get("user_token")
    }

    send(
        configuration=config,
        message='Test notification'
    )
