import os
from typing import Optional
from app.config import settings
from app.logging import get_logger

logger = get_logger()

# Global singleton instance
_supabase_service: Optional["SupabaseService"] = None


class SupabaseService:
    """Service for interacting with Supabase database."""
    
    def __init__(self):
        self._client = None
        self._is_available = False
        self._init_client()
    
    def _init_client(self):
        """Initialize the Supabase client if credentials are available."""
        url = settings.SUPABASE_URL
        key = settings.SUPABASE_KEY
        
        if not url or not key:
            logger.debug("Supabase credentials not configured. Supabase integration disabled.")
            return
        
        try:
            from supabase import create_client, Client
            self._client: Client = create_client(url, key)
            self._is_available = True
            logger.info("Supabase client initialized successfully.")
        except ImportError:
            logger.warning("supabase-py not installed. Run: pip install supabase")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
    
    @property
    def is_available(self) -> bool:
        """Check if Supabase service is available and configured."""
        return self._is_available
    
    @property
    def client(self):
        """Get the Supabase client."""
        return self._client
    
    def save_transcript(self, transcript_data: dict) -> Optional[dict]:
        """
        Save a transcript to Supabase.
        
        Args:
            transcript_data: Dictionary containing transcript data
            
        Returns:
            The inserted record or None if failed
        """
        if not self.is_available:
            logger.debug("Supabase not available, skipping save.")
            return None
        
        try:
            result = self._client.table("transcripts").insert(transcript_data).execute()
            logger.info(f"Transcript saved to Supabase: {transcript_data.get('title', 'Unknown')}")
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to save transcript to Supabase: {e}")
            return None
    
    def save_from_transcript_object(self, transcript) -> Optional[dict]:
        """
        Save a Transcript object to Supabase.
        
        Args:
            transcript: Transcript object with source metadata
            
        Returns:
            The inserted record or None if failed
        """
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
                "summary": transcript.summary if hasattr(transcript, "summary") else None,
                "media_url": source.source_file,
                "status": transcript.status,
                "conference": getattr(source, 'conference', None),
                "topics": getattr(source, 'topics', []) or [],
                "channel_name": source.youtube_metadata.get('channel_name', '') if hasattr(source, 'youtube_metadata') and source.youtube_metadata else None,
            }
            return self.save_transcript(transcript_data)
        except Exception as e:
            logger.error(f"Failed to save transcript object to Supabase: {e}")
            return None
    
    def get_transcript(self, title: str, loc: str) -> Optional[dict]:
        """
        Get a transcript from Supabase by title and location.
        
        Args:
            title: The transcript title
            loc: The location/category
            
        Returns:
            The transcript record or None if not found
        """
        if not self.is_available:
            return None
        
        try:
            result = (
                self._client.table("transcripts")
                .select("*")
                .eq("title", title)
                .eq("loc", loc)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to get transcript from Supabase: {e}")
            return None
    
    def list_transcripts(self, loc: Optional[str] = None, limit: int = 100) -> list:
        """
        List transcripts from Supabase.
        
        Args:
            loc: Optional location filter
            limit: Maximum number of results
            
        Returns:
            List of transcript records
        """
        if not self.is_available:
            return []
        
        try:
            query = self._client.table("transcripts").select("*").limit(limit)
            if loc:
                query = query.eq("loc", loc)
            result = query.execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Failed to list transcripts from Supabase: {e}")
            return []


    # =========================================================================
    # YouTube Ingestion — Channels
    # =========================================================================

    def get_active_channels(self) -> list:
        """Get all active channels ordered by priority."""
        if not self.is_available:
            return []
        try:
            result = (
                self._client.table("youtube_channels")
                .select("*")
                .eq("is_active", True)
                .order("priority")
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to get active channels: {e}")
            return []

    def get_channel_by_id(self, channel_id: str) -> Optional[dict]:
        """Get a channel by its database UUID."""
        if not self.is_available:
            return None
        try:
            result = (
                self._client.table("youtube_channels")
                .select("*")
                .eq("id", channel_id)
                .single()
                .execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"Failed to get channel {channel_id}: {e}")
            return None

    def list_channels(self) -> list:
        """List all channels."""
        if not self.is_available:
            return []
        try:
            result = (
                self._client.table("youtube_channels")
                .select("*")
                .order("channel_name")
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to list channels: {e}")
            return []

    def add_channel(self, channel_data: dict) -> Optional[dict]:
        """Insert a new channel."""
        if not self.is_available:
            return None
        try:
            result = (
                self._client.table("youtube_channels")
                .insert(channel_data)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to add channel: {e}")
            return None

    def update_channel(self, channel_id: str, updates: dict) -> Optional[dict]:
        """Update a channel by its database UUID."""
        if not self.is_available:
            return None
        try:
            result = (
                self._client.table("youtube_channels")
                .update(updates)
                .eq("id", channel_id)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to update channel {channel_id}: {e}")
            return None

    def delete_channel(self, channel_id: str) -> bool:
        """Delete a channel by its database UUID."""
        if not self.is_available:
            return False
        try:
            self._client.table("youtube_channels").delete().eq(
                "id", channel_id
            ).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to delete channel {channel_id}: {e}")
            return False

    def update_channel_scanned(self, channel_id: str):
        """Update last_scanned_at for a channel."""
        if not self.is_available:
            return
        try:
            from datetime import datetime, timezone
            self._client.table("youtube_channels").update(
                {"last_scanned_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", channel_id).execute()
        except Exception as e:
            logger.error(f"Failed to update scan time for channel {channel_id}: {e}")

    # =========================================================================
    # YouTube Ingestion — Videos
    # =========================================================================

    def insert_youtube_video(self, video_data: dict) -> Optional[dict]:
        """Insert a discovered video."""
        if not self.is_available:
            return None
        try:
            result = (
                self._client.table("youtube_videos")
                .insert(video_data)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to insert video {video_data.get('video_id')}: {e}")
            return None

    def get_existing_video_ids(self, video_ids: list[str]) -> set:
        """Check which video IDs already exist in the database."""
        if not self.is_available or not video_ids:
            return set()
        try:
            result = (
                self._client.table("youtube_videos")
                .select("video_id")
                .in_("video_id", video_ids)
                .execute()
            )
            return {row["video_id"] for row in (result.data or [])}
        except Exception as e:
            logger.error(f"Failed to check existing videos: {e}")
            return set()

    def get_videos_by_status(self, status: str, limit: int = 100) -> list:
        """Get videos filtered by status."""
        if not self.is_available:
            return []
        try:
            result = (
                self._client.table("youtube_videos")
                .select("*, youtube_channels(channel_name, category)")
                .eq("status", status)
                .order("discovered_at", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
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
        """List videos with optional filters."""
        if not self.is_available:
            return []
        try:
            query = (
                self._client.table("youtube_videos")
                .select("*, youtube_channels(channel_name, category)")
                .order("discovered_at", desc=True)
                .range(offset, offset + limit - 1)
            )
            if status:
                query = query.eq("status", status)
            if is_technical is not None:
                query = query.eq("is_technical", is_technical)
            if channel_id:
                query = query.eq("channel_id", channel_id)
            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to list youtube videos: {e}")
            return []

    def get_video_by_id(self, video_id: str) -> Optional[dict]:
        """Get a video by its database UUID, with channel info."""
        if not self.is_available:
            return None
        try:
            result = (
                self._client.table("youtube_videos")
                .select("*, youtube_channels(channel_name, category)")
                .eq("id", video_id)
                .single()
                .execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"Failed to get video {video_id}: {e}")
            return None

    def update_youtube_video(self, video_id: str, updates: dict) -> Optional[dict]:
        """Update a video by its database UUID."""
        if not self.is_available:
            return None
        try:
            result = (
                self._client.table("youtube_videos")
                .update(updates)
                .eq("id", video_id)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to update video {video_id}: {e}")
            return None

    # =========================================================================
    # YouTube Ingestion — Runs
    # =========================================================================

    def create_ingestion_run(self, **kwargs) -> Optional[dict]:
        """Create a new ingestion run record."""
        if not self.is_available:
            return None
        try:
            result = (
                self._client.table("ingestion_runs")
                .insert(kwargs)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to create ingestion run: {e}")
            return None

    def complete_ingestion_run(self, run_id: str, **kwargs) -> Optional[dict]:
        """Update a run with completion data."""
        if not self.is_available:
            return None
        try:
            result = (
                self._client.table("ingestion_runs")
                .update(kwargs)
                .eq("id", run_id)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to complete ingestion run {run_id}: {e}")
            return None

    def list_ingestion_runs(self, limit: int = 50) -> list:
        """List recent ingestion runs."""
        if not self.is_available:
            return []
        try:
            result = (
                self._client.table("ingestion_runs")
                .select("*, youtube_channels(channel_name)")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to list ingestion runs: {e}")
            return []


def get_supabase_service() -> SupabaseService:
    """
    Get the singleton SupabaseService instance.
    
    Returns:
        SupabaseService instance
    """
    global _supabase_service
    if _supabase_service is None:
        _supabase_service = SupabaseService()
    return _supabase_service
