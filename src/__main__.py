#  Copyright (c) 2025 AshokShau.
#  TgMusicBot is an open-source Telegram music bot licensed under AGPL-3.0.
#  All rights reserved where applicable.
#
#

from aiofiles import os

import config
from src import client


async def create_directories() -> None:
    """Create necessary directories."""
    from src.platforms.save_cookies import save_all_cookies
    try:
        await os.makedirs(config.DOWNLOADS_DIR, exist_ok=True)
        await os.makedirs("database/photos", exist_ok=True)
        await save_all_cookies(config.COOKIES_URL)
    except Exception as e:
        raise SystemExit(1) from e


if __name__ == "__main__":
    client.loop.create_task(create_directories())
    client.run()
