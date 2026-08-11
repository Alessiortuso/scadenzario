from .base import ChannelResult, Notifier
from .email import EmailNotifier
from .inapp import InAppNotifier
from .webpush import WebPushNotifier

# Ordine di registrazione dei canali usati dal dispatcher.
NOTIFIERS: list[Notifier] = [InAppNotifier(), WebPushNotifier(), EmailNotifier()]

__all__ = ["ChannelResult", "Notifier", "EmailNotifier", "InAppNotifier", "WebPushNotifier", "NOTIFIERS"]
