"""
A helper module for sending notifications to Pushover
"""
import http.client
import urllib


def send(configuration: dict, message: str, title: str=None):
    """Send a pushover notification

    Parameters:
        configuration (dict): {
            app_token (str): Application-specific token
            user_user (str): User token for the Pushover API
        }
        message (str): Body content of notification
        title (str): Notification title [OPTIONAL]"""
    conn = http.client.HTTPSConnection("api.pushover.net", 443)
    parameters = {
        "token": configuration["app_token"],
        "user": configuration["user_token"],
        "title": title,
        "message": message,
        "html": 1,
        "ttl": 2592000    # 30 days
    }

    # Remove the None values from the sent parameters
    for key, value in dict(parameters).items():
        if value is None:
            del parameters[key]

    conn.request(
        "POST", "/1/messages.json",
        urllib.parse.urlencode(dict(parameters)),
        {"Content-type": "application/x-www-form-urlencoded"}
    )
    conn.getresponse()

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
