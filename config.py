import os
from typing import Optional



BOT_TOKEN: str = os.getenv("BOT_TOKEN", "8291003872:AAFxBi9P-OfozsyunB9sXdl0iWBWioj7Ty0")
ADMIN_CHANNEL_ID: int = int(os.getenv("ADMIN_CHANNEL_ID", "-1003701054266"))
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "8535833319"))

# Минимальные требования для вывода
MIN_REFERRALS: int = int(os.getenv("MIN_REFERRALS", "15"))
MIN_STARS_WITHDRAW: int = int(os.getenv("MIN_STARS_WITHDRAW", "15"))

# Валидация критичных параметров
if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    raise ValueError("❌ BOT_TOKEN не установлен! Установите переменную окружения BOT_TOKEN")

if ADMIN_ID == 0:
    raise ValueError("❌ ADMIN_ID не установлен! Установите переменную окружения ADMIN_ID")

__all__ = ['BOT_TOKEN', 'ADMIN_CHANNEL_ID', 'ADMIN_ID', 'MIN_REFERRALS', 'MIN_STARS_WITHDRAW']
