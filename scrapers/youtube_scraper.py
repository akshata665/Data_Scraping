"""
YouTube Scraper — Fetches video metadata via YouTube Data API v3 and
extracts transcripts via youtube-transcript-api.
Falls back to video description if transcript unavailable.
Supports both direct watch URLs and search-result URLs.
"""

import os
import re
import logging
from typing import Optional

import requests
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
)

from utils import (
    detect_language,
    generate_topic_tags,
    chunk_content,
    now_iso,
)
from trust_engine import calculate_trust_score

logger = logging.getLogger(__name__)

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
YT_VIDEO_API = "https://www.googleapis.com/youtube/v3/videos"
YT_BASE = "https://www.youtube.com/watch?v="


# ─────────────────────────────────────────────────────────────
# VIDEO ID EXTRACTION
# ─────────────────────────────────────────────────────────────
def _extract_video_id(url: str) -> Optional[str]:
    """Extract video ID from normal watch/share/embed URLs."""
    patterns = [
        r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:embed/)([A-Za-z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def _extract_video_id_from_search(url: str) -> Optional[str]:
    """Extract first video ID from YouTube search results page."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        html = resp.text

        match = re.search(r'"videoId":"([A-Za-z0-9_-]{11})"', html)
        if match:
            return match.group(1)

    except Exception as e:
        logger.error(f"Search page video extraction failed: {e}")

    return None


# ─────────────────────────────────────────────────────────────
# METADATA
# ─────────────────────────────────────────────────────────────
def _fetch_metadata_api(video_id: str) -> Optional[dict]:
    """Fetch metadata via YouTube Data API v3."""
    if not YOUTUBE_API_KEY:
        return None

    params = {
        "part": "snippet,statistics,contentDetails",
        "id": video_id,
        "key": YOUTUBE_API_KEY,
    }

    try:
        resp = requests.get(YT_VIDEO_API, params=params, timeout=15)
        resp.raise_for_status()

        items = resp.json().get("items", [])
        if not items:
            return None

        item = items[0]
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})

        return {
            "title": snippet.get("title", "Unknown"),
            "channel": snippet.get("channelTitle", "Unknown"),
            "published_at": snippet.get("publishedAt"),
            "description": snippet.get("description", ""),
            "view_count": int(stats.get("viewCount", 0)),
            "like_count": int(stats.get("likeCount", 0)),
        }

    except Exception as e:
        logger.error(f"YouTube API fetch failed for {video_id}: {e}")
        return None


def _fetch_metadata_scrape(video_id: str) -> dict:
    """Fallback: scrape metadata directly from watch page."""
    url = f"{YT_BASE}{video_id}"

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )

        title_match = re.search(r'"title":"([^"]+)"', resp.text)
        author_match = re.search(r'"ownerChannelName":"([^"]+)"', resp.text)
        date_match = re.search(r'"publishDate":"([^"]+)"', resp.text)
        desc_match = re.search(r'"shortDescription":"([^"]+)"', resp.text)

        return {
            "title": title_match.group(1) if title_match else "Unknown",
            "channel": author_match.group(1) if author_match else "Unknown",
            "published_at": date_match.group(1) if date_match else None,
            "description": desc_match.group(1).replace("\\n", " ") if desc_match else "",
            "view_count": 0,
            "like_count": 0,
        }

    except Exception as e:
        logger.error(f"YouTube scrape fallback failed for {video_id}: {e}")
        return {
            "title": "Unknown",
            "channel": "Unknown",
            "published_at": None,
            "description": "",
            "view_count": 0,
            "like_count": 0,
        }


# ─────────────────────────────────────────────────────────────
# TRANSCRIPT
# ─────────────────────────────────────────────────────────────
def _fetch_transcript(video_id: str) -> tuple[str, bool]:
    """Fetch transcript if available."""
    try:
        ytt_api = YouTubeTranscriptApi()
        transcript_list = ytt_api.fetch(
            video_id,
            languages=["en", "en-US", "en-GB"],
        )

        text = " ".join(
            entry.text if hasattr(entry, "text") else entry["text"]
            for entry in transcript_list
        )

        return text, True

    except (TranscriptsDisabled, NoTranscriptFound):
        logger.warning(
            f"Transcript unavailable for {video_id} — using description fallback."
        )
        return "", False

    except Exception as e:
        logger.error(f"Transcript fetch error for {video_id}: {e}")
        return "", False


# ─────────────────────────────────────────────────────────────
# MAIN SCRAPER
# ─────────────────────────────────────────────────────────────
def scrape_youtube(urls: list[str]) -> list[dict]:
    """Main YouTube scraping pipeline."""
    results = []

    for url in urls:
        logger.info(f"Scraping YouTube: {url}")

        # ✅ NEW FIX: supports dynamic search URLs
        if "results?search_query=" in url:
            video_id = _extract_video_id_from_search(url)
        else:
            video_id = _extract_video_id(url)

        if not video_id:
            logger.warning(f"Could not resolve video from {url}")
            results.append({
                "source_url": url,
                "source_type": "youtube",
                "processing_status": "invalid_url",
                "pipeline_version": "v2.0",
            })
            continue

        meta = _fetch_metadata_api(video_id) or _fetch_metadata_scrape(video_id)

        transcript, transcript_available = _fetch_transcript(video_id)

        content = (
            transcript
            if transcript_available and len(transcript) > 100
            else meta["description"]
        )

        status = "success" if transcript_available else "fallback_transcript_used"

        trust_result = calculate_trust_score(
            source_url=url,
            source_type="youtube",
            author=meta["channel"],
            published_date=meta.get("published_at"),
            content=content,
            domain="youtube.com",
            citation_count=0,
            transcript_available=transcript_available,
        )

        record = {
            "source_url": url,
            "source_type": "youtube",
            "source_title": meta["title"],
            "author": meta["channel"],
            "video_id": video_id,
            "published_date": meta.get("published_at"),
            "ingestion_timestamp": now_iso(),
            "language": detect_language(content) if content else "en",
            "region": "Global",
            "topic_tags": generate_topic_tags(content, meta["title"]),
            "view_count": meta.get("view_count", 0),
            "like_count": meta.get("like_count", 0),
            "transcript_available": transcript_available,
            "trust_score": trust_result["trust_score"],
            "trust_tier": trust_result["trust_tier"],
            "confidence_score": trust_result["confidence_score"],
            "score_breakdown": trust_result["score_breakdown"],
            "score_reasoning": trust_result["score_reasoning"],
            "abuse_flags": trust_result["abuse_flags"],
            "content_chunks": chunk_content(content),
            "processing_status": status,
            "pipeline_version": trust_result["pipeline_version"],
        }

        results.append(record)

        logger.info(
            f"  ✓ YouTube '{meta['title'][:60]}' — "
            f"trust={record['trust_score']} "
            f"tier={record['trust_tier']} "
            f"transcript={transcript_available}"
        )

    return results