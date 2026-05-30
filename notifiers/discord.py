"""
A helper module for sending notifications to Discord
"""
import http.client
import json
from typing import Optional


def send(
    configuration: dict,
    message: str,
    title: Optional[str] = None,
    url: Optional[str] = None,
    url_title: Optional[str] = None,
):
    """Send a Discord webhook notification.

    Parameters:
        configuration: {'webhook_id': str, 'webhook_token': str}
        message:   Body content of notification.
        title:     Override the webhook bot username (optional).
        url:       Share link URL appended to the message (optional).
                   Discord auto-embeds the URL as a preview card.
        url_title: Ignored for Discord (URL is included inline).
    """
    content = message
    if url:
        label = url_title or "View report"
        content = f"{message}\n**[{label}]({url})**" if message else url

    payload = {
        "username": title or "AutoPkg Runner",
        "content":  content,
    }

    body = json.dumps(payload).encode()
    conn = http.client.HTTPSConnection("discord.com", 443)
    conn.request(
        "POST",
        f"/api/webhooks/{configuration['webhook_id']}/{configuration['webhook_token']}",
        body,
        {"Content-type": "application/json"},
    )
    conn.getresponse()

if __name__ == "__main__":
    import json
    from __info__ import CONFIG_FILE

    with open(CONFIG_FILE, mode="r", encoding="utf-8") as config_file:
        raw = json.load(config_file)

    settings: dict = raw["module_settings"]["core.notify"]["notifiers.discord"]

    config = {
        "webhook_id": settings.get("webhook_id"),
        "webhook_token": settings.get("webhook_token")
    }

    send(
        configuration=config,
        message='Test notification'
    )
