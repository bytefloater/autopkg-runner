"""
A helper module for sending notifications to Discord
"""
import http.client
import urllib


def send(configuration: dict, message: str, title: str=None):
    """Send a pushover notification

    Parameters:
        configuration (dict): {
            webhook_id (str): Webhook ID
            webhook_token (str): Webhook Token
        }
        message (str): Body content of notification
        title (str): Override the message username [OPTIONAL]"""
    conn = http.client.HTTPSConnection("discord.com", 443)
    parameters = {
        "username": title,
        "content": message,
    }

    # Remove the None values from the sent parameters
    for key, value in dict(parameters).items():
        if value is None:
            del parameters[key]

    conn.request(
        "POST", f"/api/webhooks/{configuration['webhook_id']}/{configuration['webhook_token']}",
        urllib.parse.urlencode(dict(parameters)),
        {"Content-type": "application/x-www-form-urlencoded"}
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
