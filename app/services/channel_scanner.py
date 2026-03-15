from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.logging import get_logger
from app.services.supabase_service import get_supabase_service

logger = get_logger()


class ChannelScanner:
    """Scans monitored YouTube channels for new videos."""

    def __init__(self):
        self._youtube = None
        self._supabase = get_supabase_service()

    @property
    def youtube(self):
        if self._youtube is None:
            from googleapiclient.discovery import build
            self._youtube = build(
                "youtube", "v3", developerKey=settings.YOUTUBE_API_KEY
            )
        return self._youtube

    def scan_all_channels(self) -> dict:
        """Scan all active channels for new videos.

        Returns:
            Summary dict with counts and any errors.
        """
        channels = self._supabase.get_active_channels()
        if not channels:
            logger.info("No active channels to scan.")
            return {"videos_discovered": 0, "errors": []}

        run = self._supabase.create_ingestion_run(
            run_type="scan", started_at=datetime.now(timezone.utc).isoformat()
        )
        run_id = run["id"] if run else None

        total_discovered = 0
        errors = []

        for channel in channels:
            try:
                count = self._scan_channel(channel)
                total_discovered += count
            except Exception as e:
                error_msg = f"Error scanning {channel['channel_name']}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        if run_id:
            self._supabase.complete_ingestion_run(
                run_id,
                videos_discovered=total_discovered,
                errors=errors,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )

        logger.info(f"Scan complete: {total_discovered} new videos discovered.")
        return {"videos_discovered": total_discovered, "errors": errors}

    def scan_channel_by_id(self, channel_db_id: str) -> dict:
        """Scan a specific channel by its database UUID.

        Args:
            channel_db_id: The UUID of the channel in youtube_channels table.

        Returns:
            Summary dict.
        """
        channel = self._supabase.get_channel_by_id(channel_db_id)
        if not channel:
            raise ValueError(f"Channel not found: {channel_db_id}")

        run = self._supabase.create_ingestion_run(
            run_type="scan",
            channel_id=channel_db_id,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        run_id = run["id"] if run else None
        errors = []

        try:
            count = self._scan_channel(channel)
        except Exception as e:
            error_msg = f"Error scanning {channel['channel_name']}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
            count = 0

        if run_id:
            self._supabase.complete_ingestion_run(
                run_id,
                videos_discovered=count,
                errors=errors,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )

        return {"videos_discovered": count, "errors": errors}

    def _scan_channel(self, channel: dict) -> int:
        """Scan a single channel and insert new videos.

        Args:
            channel: Row from youtube_channels table.

        Returns:
            Number of new videos discovered.
        """
        channel_yt_id = channel["channel_id"]
        channel_db_id = channel["id"]
        last_scanned = channel.get("last_scanned_at")

        max_results = int(
            settings.config.get("channel_scan_max_results", "50")
        )

        # Build search request
        search_params = {
            "channelId": channel_yt_id,
            "type": "video",
            "order": "date",
            "part": "id",
            "maxResults": max_results,
        }
        if last_scanned:
            search_params["publishedAfter"] = self._format_rfc3339(last_scanned)

        logger.info(f"Scanning channel: {channel['channel_name']} ({channel_yt_id})")

        # Paginate through search results
        video_ids = []
        request = self.youtube.search().list(**search_params)
        while request and len(video_ids) < max_results:
            response = request.execute()
            for item in response.get("items", []):
                vid_id = item["id"].get("videoId")
                if vid_id:
                    video_ids.append(vid_id)
            request = self.youtube.search().list_next(request, response)

        if not video_ids:
            logger.info(f"No new videos found for {channel['channel_name']}.")
            self._supabase.update_channel_scanned(channel_db_id)
            return 0

        # Filter out videos we already have
        existing = self._supabase.get_existing_video_ids(video_ids)
        new_ids = [vid for vid in video_ids if vid not in existing]

        if not new_ids:
            logger.info(f"All videos already known for {channel['channel_name']}.")
            self._supabase.update_channel_scanned(channel_db_id)
            return 0

        # Fetch full video details in batches of 50
        videos_inserted = 0
        for i in range(0, len(new_ids), 50):
            batch = new_ids[i : i + 50]
            details_response = (
                self.youtube.videos()
                .list(part="snippet,contentDetails,statistics", id=",".join(batch))
                .execute()
            )

            for item in details_response.get("items", []):
                video_data = self._parse_video_details(item, channel_db_id)
                self._supabase.insert_youtube_video(video_data)
                videos_inserted += 1

        self._supabase.update_channel_scanned(channel_db_id)
        logger.info(
            f"Discovered {videos_inserted} new videos from {channel['channel_name']}."
        )
        return videos_inserted

    def _parse_video_details(self, item: dict, channel_db_id: str) -> dict:
        """Parse a YouTube API video resource into a DB row dict."""
        snippet = item.get("snippet", {})
        content_details = item.get("contentDetails", {})
        statistics = item.get("statistics", {})

        return {
            "video_id": item["id"],
            "channel_id": channel_db_id,
            "title": snippet.get("title"),
            "description": snippet.get("description"),
            "published_at": snippet.get("publishedAt"),
            "duration": self._parse_duration(content_details.get("duration", "")),
            "tags": snippet.get("tags", []),
            "thumbnail_url": (
                snippet.get("thumbnails", {}).get("high", {}).get("url")
            ),
            "view_count": int(statistics.get("viewCount", 0)),
            "status": "pending",
        }

    @staticmethod
    def _parse_duration(duration_str: str) -> int:
        """Convert ISO 8601 duration (PT1H2M3S) to seconds."""
        if not duration_str or not duration_str.startswith("PT"):
            return 0

        duration_str = duration_str[2:]  # strip "PT"
        hours = minutes = seconds = 0

        if "H" in duration_str:
            h_part, duration_str = duration_str.split("H")
            hours = int(h_part)
        if "M" in duration_str:
            m_part, duration_str = duration_str.split("M")
            minutes = int(m_part)
        if "S" in duration_str:
            s_part, _ = duration_str.split("S")
            seconds = int(s_part)

        return hours * 3600 + minutes * 60 + seconds

    @staticmethod
    def _format_rfc3339(timestamp_str: str) -> str:
        """Ensure a timestamp is in RFC 3339 format for the YouTube API."""
        if isinstance(timestamp_str, str):
            # If it already ends with Z or has timezone info, return as-is
            if timestamp_str.endswith("Z") or "+" in timestamp_str:
                return timestamp_str
            return timestamp_str + "Z"
        return timestamp_str
