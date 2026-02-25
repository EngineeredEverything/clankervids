#!/usr/bin/env python3
"""
ClankerVids - Better Thumbnail Backfill (Option A)

1. YouTube videos: upgrade hqdefault → maxresdefault (1280px), fallback to sddefault
2. CDN-hosted Reddit videos: re-extract thumbnail at 20% of duration (not 2s mark)
"""

import os
import sqlite3
import subprocess
import tempfile
import requests
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_PATH = '/var/www/clankervids/clankervids.db'
BUNNY_STORAGE_ZONE = 'clankervids'
BUNNY_ACCESS_KEY = '9935b528-3e77-488d-9508b6340d99-1972-48bd'
BUNNY_STORAGE_URL = f'https://storage.bunnycdn.com/{BUNNY_STORAGE_ZONE}'
BUNNY_CDN_URL = f'https://{BUNNY_STORAGE_ZONE}-cdn.b-cdn.net'


# ---------------------------------------------------------------------------
# Bunny CDN helpers
# ---------------------------------------------------------------------------

def upload_to_bunny(file_path: str, remote_path: str) -> str | None:
    """Upload a local file to Bunny CDN and return the public URL."""
    try:
        with open(file_path, 'rb') as fh:
            resp = requests.put(
                f"{BUNNY_STORAGE_URL}/{remote_path}",
                data=fh,
                headers={
                    'AccessKey': BUNNY_ACCESS_KEY,
                    'Content-Type': 'application/octet-stream',
                },
                timeout=120,
            )
        if resp.status_code == 201:
            return f"{BUNNY_CDN_URL}/{remote_path}"
        logger.error(f"Bunny upload failed {resp.status_code}: {resp.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"Bunny upload error: {e}")
        return None


# ---------------------------------------------------------------------------
# YouTube: upgrade to maxresdefault
# ---------------------------------------------------------------------------

def best_youtube_thumbnail(youtube_id: str) -> str:
    """
    Return the highest-res YouTube thumbnail that actually exists.
    Priority: maxresdefault (1280px) → sddefault (640px) → hqdefault (480px)
    """
    candidates = [
        f"https://i.ytimg.com/vi/{youtube_id}/maxresdefault.jpg",
        f"https://i.ytimg.com/vi/{youtube_id}/sddefault.jpg",
        f"https://i.ytimg.com/vi/{youtube_id}/hqdefault.jpg",
    ]
    for url in candidates:
        try:
            r = requests.head(url, timeout=8, allow_redirects=True)
            # YouTube returns a tiny placeholder (< 2KB) for missing maxres thumbnails
            # with status 200, so check Content-Length too
            content_length = int(r.headers.get('Content-Length', 0))
            if r.status_code == 200 and content_length > 5000:
                return url
        except Exception:
            continue
    # Last resort fallback — always exists
    return f"https://i.ytimg.com/vi/{youtube_id}/hqdefault.jpg"


def fix_youtube_thumbnails(conn: sqlite3.Connection, dry_run: bool = False) -> int:
    """Upgrade YouTube video thumbnails to maxresdefault."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, youtube_id, thumbnail_url
        FROM videos
        WHERE status='active'
          AND youtube_id IS NOT NULL AND youtube_id != ''
    """)
    rows = cursor.fetchall()
    updated = 0

    for video_id, yt_id, current_thumb in rows:
        new_url = best_youtube_thumbnail(yt_id)
        if new_url == current_thumb:
            logger.info(f"  [yt] {yt_id} already optimal — skipping")
            continue
        logger.info(f"  [yt] {yt_id}  {current_thumb.split('/')[-1]} → {new_url.split('/')[-1]}")
        if not dry_run:
            cursor.execute(
                "UPDATE videos SET thumbnail_url=? WHERE id=?",
                (new_url, video_id)
            )
            conn.commit()
        updated += 1

    return updated


# ---------------------------------------------------------------------------
# CDN Reddit videos: re-extract at 20% duration
# ---------------------------------------------------------------------------

def get_video_duration(video_path: str) -> float | None:
    """Return video duration in seconds via ffprobe."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
             '-of', 'csv=p=0', video_path],
            capture_output=True, text=True, timeout=30
        )
        val = result.stdout.strip()
        return float(val) if val else None
    except Exception as e:
        logger.error(f"ffprobe error: {e}")
        return None


def extract_frame(video_path: str, seek_seconds: float, out_path: str) -> bool:
    """Extract a single frame at seek_seconds into out_path."""
    try:
        result = subprocess.run(
            ['ffmpeg', '-ss', str(seek_seconds), '-i', video_path,
             '-vframes', '1', '-q:v', '2', '-y', out_path],
            capture_output=True, text=True, timeout=60
        )
        return result.returncode == 0 and os.path.getsize(out_path) > 0
    except Exception as e:
        logger.error(f"ffmpeg error: {e}")
        return False


def fix_cdn_video_thumbnails(conn: sqlite3.Connection, dry_run: bool = False) -> int:
    """Re-extract thumbnails for CDN-hosted videos at 20% duration."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, video_url, thumbnail_url
        FROM videos
        WHERE status='active'
          AND video_url LIKE '%b-cdn%'
    """)
    rows = cursor.fetchall()
    updated = 0

    for video_id, video_url, current_thumb in rows:
        logger.info(f"  [cdn] {video_id[:8]}… downloading video…")

        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, 'video.mp4')
            thumb_path = os.path.join(tmpdir, 'thumb.jpg')

            # Download video from CDN
            try:
                resp = requests.get(video_url, stream=True, timeout=120)
                if resp.status_code != 200:
                    logger.warning(f"    download failed ({resp.status_code})")
                    continue
                with open(video_path, 'wb') as fh:
                    for chunk in resp.iter_content(65536):
                        fh.write(chunk)
            except Exception as e:
                logger.warning(f"    download error: {e}")
                continue

            duration = get_video_duration(video_path)
            if not duration:
                logger.warning(f"    couldn't read duration — skipping")
                continue

            seek = max(1.0, duration * 0.20)
            logger.info(f"    duration={duration:.1f}s → extracting at {seek:.1f}s (20%)")

            if not extract_frame(video_path, seek, thumb_path):
                logger.warning(f"    frame extraction failed — skipping")
                continue

            if dry_run:
                logger.info(f"    [dry-run] would upload new thumbnail for {video_id[:8]}")
                updated += 1
                continue

            # Upload to Bunny CDN (overwrite existing thumbnail)
            remote_path = f"thumbnails/{video_id}.jpg"
            new_url = upload_to_bunny(thumb_path, remote_path)
            if not new_url:
                logger.warning(f"    CDN upload failed — skipping")
                continue

            cursor.execute(
                "UPDATE videos SET thumbnail_url=? WHERE id=?",
                (new_url, video_id)
            )
            conn.commit()
            logger.info(f"    ✅ updated: {new_url}")
            updated += 1

    return updated


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import sys
    dry_run = '--dry-run' in sys.argv

    if dry_run:
        logger.info("=== DRY RUN — no changes will be written ===")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    logger.info("── YouTube thumbnails ──────────────────────────────")
    yt_updated = fix_youtube_thumbnails(conn, dry_run=dry_run)
    logger.info(f"YouTube: {yt_updated} updated")

    logger.info("── CDN Reddit video thumbnails ─────────────────────")
    cdn_updated = fix_cdn_video_thumbnails(conn, dry_run=dry_run)
    logger.info(f"CDN Reddit: {cdn_updated} updated")

    conn.close()
    logger.info(f"Done. Total updated: {yt_updated + cdn_updated}")


if __name__ == '__main__':
    main()
