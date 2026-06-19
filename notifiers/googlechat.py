"""
Send notifications to a Google Chat space via Incoming Webhook.
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
    """Send a Google Chat notification via an Incoming Webhook URL.

    Parameters:
        configuration: {'webhook_url': str}
        message:   Body content of notification.
        title:     Prepended as bold text before the message (optional).
        url:       Share-link URL appended to the message as a Markdown link
                   (optional).
        url_title: Anchor text for *url* (default "View report").
    """
    parts = []
    if title:
        parts.append(f"*{title}*")
    if message:
        parts.append(message)
    if url:
        label = url_title or "View report"
        parts.append(f"[{label}]({url})")

    text = "\n".join(parts)

    payload = {"text": text}

    parsed = urlparse(configuration['webhook_url'])
    path   = parsed.path + (f"?{parsed.query}" if parsed.query else "")

    body = json.dumps(payload).encode()
    conn = http.client.HTTPSConnection(parsed.netloc, context=ssl_context())
    conn.request("POST", path, body, {"Content-type": "application/json"})
    resp = conn.getresponse()
    if not (200 <= resp.status < 300):
        body_text = resp.read().decode(errors='replace')
        raise RuntimeError(f"Google Chat webhook returned HTTP {resp.status}: {body_text}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        prog="Google Chat Notifier (Test Entry Point)",
        description="Send a test Google Chat notification via an Incoming Webhook URL",
    )
    parser.add_argument("-w", "--webhook-url", required=True)
    args = parser.parse_args()

    send(configuration={"webhook_url": args.webhook_url}, message="Test notification")
