"""Entry point: `py main.py`. Lifespan starts the Discord bot + media cleanup."""
import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

import uvicorn

import bot
import config
import excel_store
from web import app

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("discord_bot")


def _purge_expired_media() -> int:
    cutoff = time.time() - config.MEDIA_TTL_HOURS * 3600
    removed = 0
    for name in os.listdir(config.MEDIA_DIR):
        path = os.path.join(config.MEDIA_DIR, name)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        except OSError:
            log.warning("Could not purge %s", path)
    return removed


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            n = await asyncio.to_thread(_purge_expired_media)
            if n:
                log.info("Purged %d expired media file(s)", n)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Media cleanup failed")


@asynccontextmanager
async def lifespan(app):
    excel_store.ensure_workbook(config.DATA_XLSX)
    app.state.upload_queue = asyncio.Queue()
    tasks = []
    if config.DISCORD_TOKEN and config.CHANNEL_ID:
        tasks.append(asyncio.create_task(bot.run_bot(), name="discord"))
        tasks.append(asyncio.create_task(
            bot.worker(app.state.upload_queue), name="worker"))
        log.info("Discord bot starting (channel %s)", config.CHANNEL_ID)
    else:
        log.warning("Bot disabled: set DISCORD_TOKEN and CHANNEL_ID in .env "
                    "(uploads will be saved + logged, but not posted).")
    tasks.append(asyncio.create_task(_cleanup_loop(), name="cleanup"))
    try:
        yield
    finally:
        for t in tasks:
            t.cancel()
        try:
            await bot.client.close()
        except Exception:
            pass

app.router.lifespan_context = lifespan


if __name__ == "__main__":
    uvicorn.run(app, host=config.HOST, port=config.PORT)
