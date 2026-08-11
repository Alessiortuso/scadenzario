from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import settings as env_settings
from ..models import Setting
from ..schemas import AppSettings, SettingsRead

SETTINGS_KEY = "app"


def _defaults() -> AppSettings:
    return AppSettings(
        channel_inapp=True,
        channel_push=env_settings.push_enabled,
        channel_email=env_settings.email_enabled,
        default_alert_offsets=env_settings.default_offsets,
        overdue_repeat_days=env_settings.overdue_repeat_days,
        overdue_max_reminders=env_settings.overdue_max_reminders,
        daily_send_time=env_settings.daily_send_time,
        notify_emails=[],
    )


def get_settings(db: Session) -> AppSettings:
    row = db.get(Setting, SETTINGS_KEY)
    if row is None:
        return _defaults()
    return AppSettings.model_validate({**_defaults().model_dump(), **row.value})


def save_settings(db: Session, data: AppSettings) -> AppSettings:
    row = db.get(Setting, SETTINGS_KEY)
    payload = data.model_dump(mode="json")
    if row is None:
        row = Setting(key=SETTINGS_KEY, value=payload)
        db.add(row)
    else:
        row.value = payload
    db.commit()
    return data


def to_read(data: AppSettings) -> SettingsRead:
    return SettingsRead(
        **data.model_dump(),
        push_configured=env_settings.push_enabled,
        email_configured=env_settings.email_enabled,
        timezone=env_settings.timezone,
    )
