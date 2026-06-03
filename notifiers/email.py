"""
Send notifications via SMTP email.
"""
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from notifiers._ssl import ssl_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities for a plain-text fallback."""
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    return (
        text
        .replace('&nbsp;', ' ')
        .replace('&amp;', '&')
        .replace('&lt;', '<')
        .replace('&gt;', '>')
        .replace('&quot;', '"')
        .strip()
    )


# ---------------------------------------------------------------------------
# send()
# ---------------------------------------------------------------------------

def send(
    configuration: dict,
    message: str,
    title: Optional[str] = None,
    url: Optional[str] = None,
    url_title: Optional[str] = None,
):
    """Send a notification email via SMTP.

    Parameters:
        configuration: {
            'from_address': str,
            'recipients':   str,   # comma-separated list of To: addresses
            'smtp_server':  str,
            'smtp_port':    str,   # default 587
            'use_ssl':      bool,  # True → SMTP_SSL (port 465)
                                   # False → SMTP + STARTTLS (port 587)
            'use_auth':     bool,
            'username':     str,   # required when use_auth is True
            'password':     str,   # required when use_auth is True
        }
        message:   Body content (may contain HTML).
        title:     Email subject line (optional).
        url:       Share-link URL appended to the body (optional).
        url_title: Anchor text for *url* (default "View report").
    """
    recipients = [
        r.strip()
        for r in configuration.get('recipients', '').split(',')
        if r.strip()
    ]
    if not recipients:
        raise ValueError("email notifier: no recipients configured.")

    subject = title or "AutoPkg Runner Notification"

    # Build body - plain and HTML variants
    body_html = message
    body_plain = _strip_html(message) if re.search(r'<[a-zA-Z]', message) else message

    if url:
        label = url_title or "View report"
        body_html  += f'\n<p><a href="{url}">{label}</a></p>'
        body_plain += f'\n{label}: {url}'

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = configuration['from_address']
    msg['To']      = ', '.join(recipients)
    msg.attach(MIMEText(body_plain, 'plain', 'utf-8'))
    msg.attach(MIMEText(body_html,  'html',  'utf-8'))

    host     = configuration['smtp_server']
    port     = int(configuration.get('smtp_port') or 587)
    use_ssl  = bool(configuration.get('use_ssl', False))
    ctx      = ssl_context()

    if use_ssl:
        smtp = smtplib.SMTP_SSL(host, port, context=ctx)
    else:
        smtp = smtplib.SMTP(host, port)
        try:
            smtp.starttls(context=ctx)
        except smtplib.SMTPNotSupportedError:
            # Server does not advertise STARTTLS - continue without it.
            pass

    try:
        if configuration.get('use_auth'):
            smtp.login(
                configuration.get('username', ''),
                configuration.get('password', ''),
            )
        smtp.sendmail(configuration['from_address'], recipients, msg.as_string())
    finally:
        smtp.quit()


# ---------------------------------------------------------------------------
# CLI test entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        prog="Email Notifier (Test Entry Point)",
        description="Send a test email using SMTP credentials provided in the console",
    )
    parser.add_argument("--from",       dest="from_address", required=True)
    parser.add_argument("--to",         dest="recipients",   required=True,
                        help="Comma-separated recipient addresses")
    parser.add_argument("--server",     dest="smtp_server",  required=True)
    parser.add_argument("--port",       dest="smtp_port",    default="587")
    parser.add_argument("--ssl",        action="store_true")
    parser.add_argument("--username",   default="")
    parser.add_argument("--password",   default="")
    args = parser.parse_args()

    config = {
        "from_address": args.from_address,
        "recipients":   args.recipients,
        "smtp_server":  args.smtp_server,
        "smtp_port":    args.smtp_port,
        "use_ssl":      args.ssl,
        "use_auth":     bool(args.username),
        "username":     args.username,
        "password":     args.password,
    }

    send(configuration=config, message="Test notification", title="AutoPkg Runner - Test")
