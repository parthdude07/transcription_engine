from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import joinedload

from app.database import get_session, is_db_configured
from app.logging import get_logger
from app.models import IngestionRun, Transcript, YouTubeChannel, YouTubeVideo


logger = get_logger()

# Global singleton instance
_database_service: Optional["DatabaseService"] = None


class DatabaseService:
    """Service for interacting with the PostgreSQL database via SQLAlchemy."""

    def __init__(self):
        self._is_available = is_db_configured()
        if self._is_available:
            logger.info("Database service initialized successfully.")
        else:
            logger.debug(
                "Database not configured. Database integration disabled."
            )

    @property
    def is_available(self) -> bool:
        return self._is_available

    # =========================================================================
    # Transcripts
    # =========================================================================

    def save_transcript(self, transcript_data: dict) -> Optional[dict]:
        if not self.is_available:
            logger.debug("Database not available, skipping save.")
            return None
        try:
            with get_session() as session:
                obj = Transcript(**transcript_data)
                session.add(obj)
                session.flush()
                result = obj.to_dict()
            logger.info(
                f"Transcript saved: {transcript_data.get('title', 'Unknown')}"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to save transcript: {e}")
            return None

    def save_from_transcript_object(self, transcript) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            source = transcript.source
            transcript_data = {
                "title": source.title,
                "loc": source.loc,
                "event_date": str(source.date) if source.date else None,
                "speakers": source.speakers if source.speakers else [],
                "tags": source.tags if source.tags else [],
                "categories": source.category if source.category else [],
                "raw_text": transcript.outputs.get("raw", ""),
                "corrected_text": transcript.outputs.get("corrected_text", ""),
                "summary": transcript.summary
                if hasattr(transcript, "summary")
                else None,
                "media_url": source.source_file,
                "status": transcript.status,
                "conference": getattr(source, "conference", None),
                "topics": getattr(source, "topics", []) or [],
                "channel_name": (
                    source.youtube_metadata.get("channel_name", "")
                    if hasattr(source, "youtube_metadata")
                    and source.youtube_metadata
                    else None
                ),
            }
            return self.save_transcript(transcript_data)
        except Exception as e:
            logger.error(f"Failed to save transcript object: {e}")
            return None

    def get_transcript(self, title: str, loc: str) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = (
                    session.query(Transcript)
                    .filter_by(title=title, loc=loc)
                    .first()
                )
                return obj.to_dict() if obj else None
        except Exception as e:
            logger.error(f"Failed to get transcript: {e}")
            return None

    def list_transcripts(
        self, loc: Optional[str] = None, limit: int = 100
    ) -> list:
        if not self.is_available:
            return []
        try:
            with get_session() as session:
                query = session.query(Transcript).limit(limit)
                if loc:
                    query = query.filter_by(loc=loc)
                return [obj.to_dict() for obj in query.all()]
        except Exception as e:
            logger.error(f"Failed to list transcripts: {e}")
            return []

    def get_all_transcripts(self, limit: int = 100, offset: int = 0) -> list:
        if not self.is_available:
            return []
        try:
            with get_session() as session:
                objs = (
                    session.query(Transcript)
                    .order_by(Transcript.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )
                return [obj.to_dict() for obj in objs]
        except Exception as e:
            logger.error(f"Failed to get all transcripts: {e}")
            return []

    def get_transcript_by_id(self, transcript_id: str) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = (
                    session.query(Transcript)
                    .filter_by(id=transcript_id)
                    .first()
                )
                return obj.to_dict() if obj else None
        except Exception as e:
            logger.error(f"Failed to get transcript {transcript_id}: {e}")
            return None

    def get_corrected_transcripts(
        self, limit: int = 100, offset: int = 0
    ) -> list:
        if not self.is_available:
            return []
        try:
            with get_session() as session:
                objs = (
                    session.query(Transcript)
                    .filter(Transcript.corrected_text.isnot(None))
                    .order_by(Transcript.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )
                return [obj.to_dict() for obj in objs]
        except Exception as e:
            logger.error(f"Failed to get corrected transcripts: {e}")
            return []

    def get_summaries(self, limit: int = 100, offset: int = 0) -> list:
        if not self.is_available:
            return []
        try:
            with get_session() as session:
                objs = (
                    session.query(Transcript)
                    .filter(Transcript.summary.isnot(None))
                    .order_by(Transcript.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )
                return [obj.to_dict() for obj in objs]
        except Exception as e:
            logger.error(f"Failed to get summaries: {e}")
            return []

    # =========================================================================
    # YouTube Channels
    # =========================================================================

    def get_active_channels(self) -> list:
        if not self.is_available:
            return []
        try:
            with get_session() as session:
                objs = (
                    session.query(YouTubeChannel)
                    .filter_by(is_active=True)
                    .order_by(YouTubeChannel.priority)
                    .all()
                )
                return [obj.to_dict() for obj in objs]
        except Exception as e:
            logger.error(f"Failed to get active channels: {e}")
            return []

    def get_channel_by_id(self, channel_id: str) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = (
                    session.query(YouTubeChannel)
                    .filter_by(id=channel_id)
                    .first()
                )
                return obj.to_dict() if obj else None
        except Exception as e:
            logger.error(f"Failed to get channel {channel_id}: {e}")
            return None

    def get_channel_by_yt_id(self, yt_channel_id: str) -> Optional[dict]:
        """Look up a channel by its YouTube channel ID (not the database UUID)."""
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = (
                    session.query(YouTubeChannel)
                    .filter_by(channel_id=yt_channel_id)
                    .first()
                )
                return obj.to_dict() if obj else None
        except Exception as e:
            logger.error(f"Failed to get channel by YT ID {yt_channel_id}: {e}")
            return None

    def list_channels(self) -> list:
        if not self.is_available:
            return []
        try:
            with get_session() as session:
                objs = (
                    session.query(YouTubeChannel)
                    .order_by(YouTubeChannel.channel_name)
                    .all()
                )
                return [obj.to_dict() for obj in objs]
        except Exception as e:
            logger.error(f"Failed to list channels: {e}")
            return []

    def add_channel(self, channel_data: dict) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = YouTubeChannel(**channel_data)
                session.add(obj)
                session.flush()
                return obj.to_dict()
        except Exception as e:
            logger.error(f"Failed to add channel: {e}")
            return None

    def update_channel(self, channel_id: str, updates: dict) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = (
                    session.query(YouTubeChannel)
                    .filter_by(id=channel_id)
                    .first()
                )
                if not obj:
                    return None
                for key, value in updates.items():
                    setattr(obj, key, value)
                session.flush()
                return obj.to_dict()
        except Exception as e:
            logger.error(f"Failed to update channel {channel_id}: {e}")
            return None

    def delete_channel(self, channel_id: str) -> bool:
        if not self.is_available:
            return False
        try:
            with get_session() as session:
                obj = (
                    session.query(YouTubeChannel)
                    .filter_by(id=channel_id)
                    .first()
                )
                if not obj:
                    return False
                session.delete(obj)
                return True
        except Exception as e:
            logger.error(f"Failed to delete channel {channel_id}: {e}")
            return False

    def update_channel_scanned(self, channel_id: str):
        if not self.is_available:
            return
        try:
            with get_session() as session:
                obj = (
                    session.query(YouTubeChannel)
                    .filter_by(id=channel_id)
                    .first()
                )
                if obj:
                    obj.last_scanned_at = datetime.now(timezone.utc)
        except Exception as e:
            logger.error(
                f"Failed to update scan time for channel {channel_id}: {e}"
            )

    # =========================================================================
    # YouTube Videos
    # =========================================================================

    def insert_youtube_video(self, video_data: dict) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = YouTubeVideo(**video_data)
                session.add(obj)
                session.flush()
                return obj.to_dict()
        except Exception as e:
            logger.error(
                f"Failed to insert video {video_data.get('video_id')}: {e}"
            )
            return None

    def get_existing_video_ids(self, video_ids: list[str]) -> set:
        if not self.is_available or not video_ids:
            return set()
        try:
            with get_session() as session:
                rows = (
                    session.query(YouTubeVideo.video_id)
                    .filter(YouTubeVideo.video_id.in_(video_ids))
                    .all()
                )
                return {row[0] for row in rows}
        except Exception as e:
            logger.error(f"Failed to check existing videos: {e}")
            return set()

    def get_videos_by_status(self, status: str, limit: int = 100) -> list:
        if not self.is_available:
            return []
        try:
            with get_session() as session:
                objs = (
                    session.query(YouTubeVideo)
                    .options(joinedload(YouTubeVideo.channel))
                    .filter(YouTubeVideo.status == status)
                    .order_by(YouTubeVideo.discovered_at.desc())
                    .limit(limit)
                    .all()
                )
                return [obj.to_dict(include_channel=True) for obj in objs]
        except Exception as e:
            logger.error(f"Failed to get videos by status '{status}': {e}")
            return []

    def list_youtube_videos(
        self,
        status: Optional[str] = None,
        is_technical: Optional[bool] = None,
        channel_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list:
        if not self.is_available:
            return []
        try:
            with get_session() as session:
                query = (
                    session.query(YouTubeVideo)
                    .options(joinedload(YouTubeVideo.channel))
                    .order_by(YouTubeVideo.discovered_at.desc())
                )
                if status:
                    query = query.filter(YouTubeVideo.status == status)
                if is_technical is not None:
                    query = query.filter(
                        YouTubeVideo.is_technical == is_technical
                    )
                if channel_id:
                    query = query.filter(YouTubeVideo.channel_id == channel_id)
                objs = query.offset(offset).limit(limit).all()
                return [obj.to_dict(include_channel=True) for obj in objs]
        except Exception as e:
            logger.error(f"Failed to list youtube videos: {e}")
            return []

    def get_video_by_id(self, video_id: str) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = (
                    session.query(YouTubeVideo)
                    .options(joinedload(YouTubeVideo.channel))
                    .filter_by(id=video_id)
                    .first()
                )
                return obj.to_dict(include_channel=True) if obj else None
        except Exception as e:
            logger.error(f"Failed to get video {video_id}: {e}")
            return None

    def update_youtube_video(
        self, video_id: str, updates: dict
    ) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = session.query(YouTubeVideo).filter_by(id=video_id).first()
                if not obj:
                    return None
                for key, value in updates.items():
                    setattr(obj, key, value)
                session.flush()
                return obj.to_dict()
        except Exception as e:
            logger.error(f"Failed to update video {video_id}: {e}")
            return None

    # =========================================================================
    # Ingestion Runs
    # =========================================================================

    def create_ingestion_run(self, **kwargs) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = IngestionRun(**kwargs)
                session.add(obj)
                session.flush()
                return obj.to_dict()
        except Exception as e:
            logger.error(f"Failed to create ingestion run: {e}")
            return None

    def complete_ingestion_run(self, run_id: str, **kwargs) -> Optional[dict]:
        if not self.is_available:
            return None
        try:
            with get_session() as session:
                obj = session.query(IngestionRun).filter_by(id=run_id).first()
                if not obj:
                    return None
                for key, value in kwargs.items():
                    setattr(obj, key, value)
                session.flush()
                return obj.to_dict()
        except Exception as e:
            logger.error(f"Failed to complete ingestion run {run_id}: {e}")
            return None

    def list_ingestion_runs(self, limit: int = 50) -> list:
        if not self.is_available:
            return []
        try:
            with get_session() as session:
                objs = (
                    session.query(IngestionRun)
                    .options(joinedload(IngestionRun.channel))
                    .order_by(IngestionRun.created_at.desc())
                    .limit(limit)
                    .all()
                )
                return [obj.to_dict(include_channel=True) for obj in objs]
        except Exception as e:
            logger.error(f"Failed to list ingestion runs: {e}")
            return []


def get_database_service() -> DatabaseService:
    """Get the singleton DatabaseService instance."""
    global _database_service
    if _database_service is None:
        _database_service = DatabaseService()
    return _database_service
