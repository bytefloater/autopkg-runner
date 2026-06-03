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
                   Pushover opens this URL when the notification is tapped -
                   use a share link so the in-app browser opens the report.
        url_title: Display label for *url* (optional; defaults to "View report").
    """
    conn = http.client.HTTPSConnection("api.pushover.net", 443, context=ssl_context())
    parameters = {
        "token":     configuration["app_token"],
        "user":      configuration["user_token"],
        "title":     title,
        "message":   message,
        "ttl":       2592000,   # 30 days
        "url":       url,
        "url_title": url_title or ("View report" if url else None),
    }

    # Enable Pushover's HTML rendering only when the notifier is configured to
    # send HTML messages.  When False (plain text), omitting the parameter lets
    # Pushover display the message as-is without attempting HTML parsing.
    if configuration.get('supports_html'):
        parameters['html'] = 1

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
    import argparse

    parser = argparse.ArgumentParser(
        prog="Pushover Notifier (Test Entry Point)",
        description="Send a test Pushover notification using the tokens provided in the console"
    )
    parser.add_argument("-a", "--app-token", required=True)
    parser.add_argument("-u", "--user-token", required=True)
    args = parser.parse_args()

    config = {
        "app_token": args.app_token,
        "user_token": args.user_token
    }

    send(
        configuration=config,
        message='Test notification'
    )
