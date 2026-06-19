"""
Send notifications to a Slack channel via Incoming Webhook.
"""
import http.client
import json
from typing import Optional
from urllib.parse import urlparse

from notifiers._ssl import ssl_context


def send(
    configuration: dict,
    message: str,
    title: Optional[str] = None,
    url: Optional[str] = None,
    url_title: Optional[str] = None,
):
    """Send a Slack notification via an Incoming Webhook URL.

    Parameters:
        configuration: {'webhook_url': str}
        message:   Body content of notification.
        title:     Overrides the webhook's default bot username (optional).
        url:       Share-link URL appended to the message (optional).
                   Rendered as a Slack mrkdwn link: <URL|label>.
        url_title: Anchor text for *url* (default "View report").
    """
    text = message
    if url:
        label = url_title or "View report"
        link  = f"<{url}|{label}>"
        text  = f"{message}\n{link}" if message else link

    payload: dict = {"text": text}
    if title:
        payload["username"] = title

    parsed = urlparse(configuration['webhook_url'])
    path   = parsed.path + (f"?{parsed.query}" if parsed.query else "")

    body = json.dumps(payload).encode()
    conn = http.client.HTTPSConnection(parsed.netloc, context=ssl_context())
    conn.request("POST", path, body, {"Content-type": "application/json"})
    resp = conn.getresponse()
    if not (200 <= resp.status < 300):
        body_text = resp.read().decode(errors='replace')
        raise RuntimeError(f"Slack webhook returned HTTP {resp.status}: {body_text}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        prog="Slack Notifier (Test Entry Point)",
        description="Send a test Slack notification via an Incoming Webhook URL",
    )
    parser.add_argument("-w", "--webhook-url", required=True)
    args = parser.parse_args()

    send(configuration={"webhook_url": args.webhook_url}, message="Test notification")
