"""Non-blocking operator notifications for long-running tome builds."""
import os
import sys
import threading
import urllib.parse
import urllib.request

from ..config import read_settings


def _pushover_creds():
    token, user = os.environ.get("PUSHOVER_TOKEN"), os.environ.get("PUSHOVER_USER")
    if not (token and user):
        settings = read_settings().get("pushover") or {}
        token, user = token or settings.get("token"), user or settings.get("user")
    return (token, user) if token and user else None


def notify(title, message, priority=0):
    """Send without blocking or breaking the build; missing credentials are a no-op."""
    credentials = _pushover_creds()
    if not credentials:
        return
    token, user = credentials

    def send():
        try:
            data = urllib.parse.urlencode({"token": token, "user": user,
                                           "title": title[:250], "message": message[:1024],
                                           "priority": priority}).encode()
            urllib.request.urlopen("https://api.pushover.net/1/messages.json", data=data,
                                   timeout=10)
        except Exception as exc:
            print(f"pushover: {exc}", file=sys.stderr)

    threading.Thread(target=send, daemon=True).start()
