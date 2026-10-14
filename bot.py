"""discord.py client + background worker that posts queued uploads.

Small files (<= DISCORD_UPLOAD_LIMIT) go as message attachments
(batched, max 10 per message, then deleted locally).
Big files stay in media/ and are posted as self-hosted links.
Every outcome is written back to the Excel log.
"""
import asyncio
import logging
import os

import discord

import config
import excel_store

log = logging.getLogger("discord_bot")

intents = discord.Intents.default()
client = discord.Client(intents=intents)


def _mb(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB"


def media_url(stored_name: str) -> str:
    return f"{config.PUBLIC_BASE_URL}/media/{stored_name}"


async def _mark(row: int, **fields) -> None:
    if not row:
        return
    try:
        await asyncio.to_thread(excel_store.update_row, config.DATA_XLSX, row, fields)
    except Exception:
        log.exception("Excel update failed for row %s", row)


async def _resolve_channel():
    if not config.CHANNEL_ID:
        raise RuntimeError("CHANNEL_ID is not set in .env")
    await client.wait_until_ready()
    channel = client.get_channel(config.CHANNEL_ID)
    if channel is None:
        channel = await client.fetch_channel(config.CHANNEL_ID)
    return channel


async def _send_attachments(channel, items: list) -> None:
    """Send small files as attachments, 10 per message. Deletes files on success."""
    for i in range(0, len(items), 10):
        group = items[i:i + 10]
        files = []
        sent_ok = False
        try:
            for it in group:
                path = os.path.join(config.MEDIA_DIR, it["stored_name"])
                files.append(discord.File(path, filename=it["original_name"]))
            caption = "\n".join(
                f"\U0001F4CE {it['original_name']} ({_mb(it['size_bytes'])})"
                for it in group
            )
            msg = await channel.send(content=caption[:1900] or None, files=files)
            sent_ok = True
            for it in group:
                await _mark(it.get("row"), mode="attachment", url="",
                            message_id=str(msg.id), status="sent", error="")
        except Exception as exc:
            log.exception("Attachment batch failed")
            for it in group:
                await _mark(it.get("row"), mode="attachment", status="failed",
                            error=str(exc)[:500])
        finally:
            for f in files:
                try:
                    f.close()
                except Exception:
                    pass
        if sent_ok:
            # Files posted to Discord; remove local copies (links are kept).
            for it in group:
                path = os.path.join(config.MEDIA_DIR, it["stored_name"])
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    log.warning("Could not delete %s", path)


async def _send_links(channel, items: list) -> None:
    """Post big files as self-hosted URLs. Files stay in media/."""
    lines = []
    for it in items:
        url = media_url(it["stored_name"])
        it["_url"] = url
        lines.append(f"\U0001F517 {it['original_name']} ({_mb(it['size_bytes'])})\n{url}")
    # Chunk lines so each message stays under 2000 chars.
    chunks, current = [], ""
    for line in lines:
        candidate = (current + "\n\n" + line).strip()
        if len(candidate) > 1900 and current:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    # Map chunk -> items by rebuilding from lines (simple: resend per chunk
    # using the same order and slice by cumulative length).
    idx = 0
    for chunk in chunks:
        try:
            msg = await channel.send(content=chunk)
            # Attribute this message id to every item whose line is in chunk.
            for it in items[idx:]:
                if it["_url"] in chunk:
                    await _mark(it.get("row"), mode="link", url=it["_url"],
                                message_id=str(msg.id), status="sent", error="")
                    idx += 1
                else:
                    break
        except Exception as exc:
            log.exception("Link message failed")
            for it in items[idx:]:
                if it["_url"] in chunk:
                    await _mark(it.get("row"), mode="link", url=it["_url"],
                                status="failed", error=str(exc)[:500])
                    idx += 1
                else:
                    break


async def _process_job(channel, job: dict) -> None:
    items = job.get("items", [])
    if not items:
        return
    small = [it for it in items if it["size_bytes"] <= config.DISCORD_UPLOAD_LIMIT_BYTES]
    big = [it for it in items if it["size_bytes"] > config.DISCORD_UPLOAD_LIMIT_BYTES]
    if small:
        await _send_attachments(channel, small)
    if big:
        await _send_links(channel, big)


async def worker(queue: asyncio.Queue) -> None:
    channel = await _resolve_channel()
    log.info("Bot worker ready, target channel %s", config.CHANNEL_ID)
    while True:
        job = await queue.get()
        try:
            await _process_job(channel, job)
        except Exception:
            log.exception("Job failed")
            for it in job.get("items", []):
                await _mark(it.get("row"), status="failed", error="worker error")
        finally:
            queue.task_done()


async def run_bot() -> None:
    if not config.DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set in .env")
    await client.start(config.DISCORD_TOKEN)
