from dataclasses import dataclass
from typing import Optional

from settings import BOT_TOKEN, DEFAULT_TIMEZONE


@dataclass(frozen=True)
class BotConfig:
    token: str
    default_timezone: str


def load_config() -> BotConfig:
    if BOT_TOKEN is None:
        raise RuntimeError("BOT_TOKEN не сконфигурирован")

    return BotConfig(
        token=BOT_TOKEN,
        default_timezone=DEFAULT_TIMEZONE,
    )

