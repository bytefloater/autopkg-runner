"""
A helper module for sending notifications to Discord
"""
import http.client
import json
from typing import Optional

from notifiers._ssl import ssl_context


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
    conn = http.client.HTTPSConnection("discord.com", 443, context=ssl_context())
    conn.request(
        "POST",
        f"/api/webhooks/{configuration['webhook_id']}/{configuration['webhook_token']}",
        body,
        {"Content-type": "application/json"},
    )
    resp = conn.getresponse()
    if not (200 <= resp.status < 300):
        body_text = resp.read().decode(errors='replace')
        raise RuntimeError(f"Discord webhook returned HTTP {resp.status}: {body_text}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        prog="Discord Notifier (Test Entry Point)",
        description="Send a test Discord notification using the tokens provided in the console"
    )
    parser.add_argument("-i", "--webhook-id", required=True)
    parser.add_argument("-t", "--webhook-token", required=True)
    args = parser.parse_args()

    config = {
        "webhook_id": args.webhook_id,
        "webhook_token": args.webhook_token
    }

    send(
        configuration=config,
        message='Test notification'
    )
