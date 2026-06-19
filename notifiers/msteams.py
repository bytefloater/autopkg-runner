"""
Send notifications to a Microsoft Teams channel via Incoming Webhook.
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
    """Send a Microsoft Teams notification via an Incoming Webhook URL.

    Uses the legacy MessageCard format which is supported by all Teams
    Incoming Webhook connectors.

    Parameters:
        configuration: {'webhook_url': str}
        message:   Body content of notification.
        title:     Card title (optional; defaults to "AutoPkg Runner").
        url:       Share-link URL added as an OpenUri action button (optional).
        url_title: Button label for *url* (default "View report").
    """
    card_title = title or "AutoPkg Runner"

    payload: dict = {
        "@type":    "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary":  card_title,
        "sections": [
            {
                "activityTitle": card_title,
                "activityText":  message,
            }
        ],
    }

    if url:
        label = url_title or "View report"
        payload["potentialAction"] = [
            {
                "@type":   "OpenUri",
                "name":    label,
                "targets": [{"os": "default", "uri": url}],
            }
        ]

    parsed = urlparse(configuration['webhook_url'])
    path   = parsed.path + (f"?{parsed.query}" if parsed.query else "")

    body = json.dumps(payload).encode()
    conn = http.client.HTTPSConnection(parsed.netloc, context=ssl_context())
    conn.request("POST", path, body, {"Content-type": "application/json"})
    resp = conn.getresponse()
    if not (200 <= resp.status < 300):
        body_text = resp.read().decode(errors='replace')
        raise RuntimeError(f"Teams webhook returned HTTP {resp.status}: {body_text}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        prog="MS Teams Notifier (Test Entry Point)",
        description="Send a test Microsoft Teams notification via an Incoming Webhook URL",
    )
    parser.add_argument("-w", "--webhook-url", required=True)
    args = parser.parse_args()

    send(configuration={"webhook_url": args.webhook_url}, message="Test notification")
