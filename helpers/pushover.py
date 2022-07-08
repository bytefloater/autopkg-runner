"""
A helper module for sending notifications to Pushover
"""
import http.client
import urllib


def send(token: str, user: str, message: str, title: str=None):
    """Send a pushover notification

    Parameters:
        token (str): Application-specific token
        user (str): User token for the Pushover API
        message (str): Body content of notification
        title (str): Notification title [OPTIONAL]"""
    conn = http.client.HTTPSConnection("api.pushover.net:443")
    parameters = {
        "token": token,
        "user": user,
        "title": title,
        "message": message,
        "html": 1
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
    send(
        token="",
        user="",
        message='Test notification'
    )
