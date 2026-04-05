import logging as syslogging

import click
import requests

from app import logging
from app.commands.cli_utils import get_transcription_url


logger = logging.get_logger()


@click.group()
def ingest():
    """Automated YouTube ingestion commands."""
    logging.configure_logger(log_level=syslogging.INFO)


@ingest.command()
def scan():
    """Scan all active channels for new videos."""
    url = get_transcription_url()
    try:
        response = requests.post(f"{url}/ingestion/scan")
        result = response.json()
        if response.status_code == 200:
            logger.info(
                f"Scan complete: {result.get('videos_discovered', 0)} new videos discovered."
            )
            errors = result.get("errors", [])
            if errors:
                for err in errors:
                    logger.warning(f"  Error: {err}")
        else:
            logger.error(
                f"Scan failed: {result.get('detail', 'Unknown error')}"
            )
    except Exception as e:
        logger.error(f"Scan request failed: {e}")


@ingest.command()
def classify():
    """Classify all pending videos using LLM."""
    url = get_transcription_url()
    try:
        response = requests.post(f"{url}/ingestion/classify")
        result = response.json()
        if response.status_code == 200:
            logger.info(
                f"Classification complete: "
                f"{result.get('videos_classified', 0)} classified, "
                f"{result.get('videos_approved', 0)} approved, "
                f"{result.get('videos_rejected', 0)} rejected."
            )
            errors = result.get("errors", [])
            if errors:
                for err in errors:
                    logger.warning(f"  Error: {err}")
        else:
            logger.error(
                f"Classification failed: {result.get('detail', 'Unknown error')}"
            )
    except Exception as e:
        logger.error(f"Classification request failed: {e}")


@ingest.command()
def run():
    """Run full pipeline: scan → classify → queue approved videos."""
    url = get_transcription_url()
    try:
        response = requests.post(f"{url}/ingestion/run")
        result = response.json()
        if response.status_code == 200:
            scan = result.get("scan", {})
            classify_data = result.get("classify", {})
            queue = result.get("queue", {})

            logger.info("Full ingestion pipeline complete:")
            logger.info(
                f"  Scan: {scan.get('videos_discovered', 0)} videos discovered"
            )
            logger.info(
                f"  Classify: {classify_data.get('videos_approved', 0)} approved, "
                f"{classify_data.get('videos_rejected', 0)} rejected"
            )
            logger.info(
                f"  Queue: {queue.get('videos_queued', 0)} videos sent to pipeline"
            )
        else:
            logger.error(
                f"Pipeline failed: {result.get('detail', 'Unknown error')}"
            )
    except Exception as e:
        logger.error(f"Pipeline request failed: {e}")


# ── Channel subcommands ─────────────────────────────────────────────────────


@ingest.group()
def channels():
    """Manage monitored YouTube channels."""
    pass


@channels.command(name="list")
def list_channels():
    """List all monitored channels."""
    url = get_transcription_url()
    try:
        response = requests.get(f"{url}/ingestion/channels")
        result = response.json()
        data = result.get("data", [])
        if not data:
            logger.info("No channels configured.")
            return
        for ch in data:
            active = "active" if ch.get("is_active") else "inactive"
            logger.info(
                f"  [{active}] {ch['channel_name']} "
                f"(priority: {ch.get('priority', '-')}, "
                f"category: {ch.get('category', '-')}, "
                f"id: {ch['id']})"
            )
    except Exception as e:
        logger.error(f"Failed to list channels: {e}")


@channels.command(name="add")
@click.argument("channel_id")
@click.argument("channel_name")
@click.option(
    "--category",
    default=None,
    help="Channel category (e.g., conference, podcast)",
)
@click.option(
    "--priority", default=3, type=int, help="Priority 1 (high) to 5 (low)"
)
@click.option(
    "--url", "channel_url", default=None, help="Full YouTube channel URL"
)
def add_channel(channel_id, channel_name, category, priority, channel_url):
    """Add a YouTube channel to monitor. Requires CHANNEL_ID and CHANNEL_NAME."""
    url = get_transcription_url()
    payload = {
        "channel_id": channel_id,
        "channel_name": channel_name,
        "priority": priority,
    }
    if category:
        payload["category"] = category
    if channel_url:
        payload["channel_url"] = channel_url

    try:
        response = requests.post(f"{url}/ingestion/channels", json=payload)
        result = response.json()
        if response.status_code == 200:
            logger.info(f"Channel added: {channel_name}")
        else:
            logger.error(f"Failed: {result.get('detail', 'Unknown error')}")
    except Exception as e:
        logger.error(f"Failed to add channel: {e}")


# ── Video subcommands ────────────────────────────────────────────────────────


@ingest.group()
def videos():
    """View and manage discovered videos."""
    pass


@videos.command(name="list")
@click.option(
    "--status",
    default=None,
    help="Filter by status (pending, classified, queued, transcribed, skipped)",
)
@click.option(
    "--technical/--non-technical",
    default=None,
    help="Filter by technical classification",
)
@click.option("--limit", default=50, type=int, help="Max results to show")
def list_videos(status, technical, limit):
    """List discovered videos."""
    url = get_transcription_url()
    params = {"limit": limit}
    if status:
        params["status"] = status
    if technical is not None:
        params["is_technical"] = technical

    try:
        response = requests.get(f"{url}/ingestion/videos", params=params)
        result = response.json()
        data = result.get("data", [])
        if not data:
            logger.info("No videos found matching filters.")
            return
        for v in data:
            tech = (
                "technical"
                if v.get("is_technical")
                else (
                    "non-technical"
                    if v.get("is_technical") is False
                    else "unclassified"
                )
            )
            logger.info(
                f"  [{v.get('status', '?')}] [{tech}] "
                f"{v.get('title', 'No title')[:70]} "
                f"(id: {v['id']})"
            )
    except Exception as e:
        logger.error(f"Failed to list videos: {e}")


@videos.command(name="approve")
@click.argument("video_id")
@click.option("--reason", default=None, help="Reason for approval")
def approve_video(video_id, reason):
    """Manually approve a video for transcription."""
    url = get_transcription_url()
    payload = {"is_technical": True}
    if reason:
        payload["classification_reason"] = reason

    try:
        response = requests.put(
            f"{url}/ingestion/videos/{video_id}", json=payload
        )
        result = response.json()
        if response.status_code == 200:
            logger.info("Video approved and queued for transcription.")
        else:
            logger.error(f"Failed: {result.get('detail', 'Unknown error')}")
    except Exception as e:
        logger.error(f"Failed to approve video: {e}")


@videos.command(name="reject")
@click.argument("video_id")
@click.option("--reason", default=None, help="Reason for rejection")
def reject_video(video_id, reason):
    """Manually reject a video."""
    url = get_transcription_url()
    payload = {"is_technical": False}
    if reason:
        payload["classification_reason"] = reason

    try:
        response = requests.put(
            f"{url}/ingestion/videos/{video_id}", json=payload
        )
        result = response.json()
        if response.status_code == 200:
            logger.info("Video rejected and skipped.")
        else:
            logger.error(f"Failed: {result.get('detail', 'Unknown error')}")
    except Exception as e:
        logger.error(f"Failed to reject video: {e}")


commands = ingest
