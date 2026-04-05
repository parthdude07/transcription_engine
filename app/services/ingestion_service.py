from app.logging import get_logger
from app.services.channel_scanner import ChannelScanner
from app.services.content_classifier import ContentClassifier
from app.services.database_service import get_database_service


logger = get_logger()


class IngestionService:
    """Orchestrates the full ingestion pipeline."""

    def __init__(self):
        self._db = get_database_service()

    def run_full_pipeline(self) -> dict:
        """Execute the full pipeline: scan → classify → queue approved videos.

        Returns:
            Combined summary of all stages.
        """
        logger.info("Starting full ingestion pipeline...")

        # Stage 1: Scan
        logger.info("Stage 1: Scanning channels for new videos...")
        scanner = ChannelScanner()
        scan_result = scanner.scan_all_channels()
        logger.info(
            f"Scan complete: {scan_result['videos_discovered']} videos discovered."
        )

        # Stage 2: Classify
        logger.info("Stage 2: Classifying pending videos...")
        classifier = ContentClassifier()
        classify_result = classifier.classify_all_pending()
        logger.info(
            f"Classification complete: {classify_result['videos_approved']} approved, "
            f"{classify_result['videos_rejected']} rejected."
        )

        # Stage 3: Queue approved videos into transcription pipeline
        logger.info("Stage 3: Queueing approved videos for transcription...")
        queue_result = self.queue_approved_videos()
        logger.info(
            f"Queueing complete: {queue_result['videos_queued']} videos sent to pipeline."
        )

        summary = {
            "scan": scan_result,
            "classify": classify_result,
            "queue": queue_result,
        }

        all_errors = (
            scan_result.get("errors", [])
            + classify_result.get("errors", [])
            + queue_result.get("errors", [])
        )
        if all_errors:
            logger.warning(
                f"Pipeline completed with {len(all_errors)} error(s)."
            )

        logger.info("Full ingestion pipeline complete.")
        return summary

    def queue_approved_videos(self, limit: int = 20) -> dict:
        """Queue approved videos into the transcription pipeline.

        Fetches videos with status 'queued' and submits them to the
        transcription API endpoint.

        Args:
            limit: Max number of videos to queue per run.

        Returns:
            Summary dict with counts and errors.
        """
        videos = self._db.get_videos_by_status("queued", limit=limit)
        if not videos:
            logger.info("No approved videos to queue for transcription.")
            return {"videos_queued": 0, "errors": []}

        queued = 0
        errors = []

        for video in videos:
            try:
                self._submit_to_pipeline(video)
                queued += 1
            except Exception as e:
                error_msg = f"Failed to queue '{video.get('title', video['video_id'])}': {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        return {"videos_queued": queued, "errors": errors}

    def _submit_to_pipeline(self, video: dict):
        """Submit a single video to the transcription pipeline via internal API.

        Args:
            video: Row from youtube_videos table with joined channel data.
        """
        video_id = video["video_id"]
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"

        channel_info = video.get("youtube_channels") or {}
        channel_category = channel_info.get("category", "misc")

        import requests

        from app.config import settings

        server_url = (
            settings.TRANSCRIPTION_SERVER_URL or "http://localhost:8000"
        )

        data = {
            "source": youtube_url,
            "loc": channel_category,
            "deepgram": True,
            "diarize": True,
            "markdown": True,
            "correct": True,
        }

        # Add to queue
        response = requests.post(
            f"{server_url}/transcription/add_to_queue/", data=data
        )
        response.raise_for_status()

        # Update video status
        self._db.update_youtube_video(
            video["id"],
            {"status": "transcribed"},
        )

        logger.info(f"Queued for transcription: {video.get('title', video_id)}")
