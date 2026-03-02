"""
bunny_thumb.py — Thumbnail upload helper for BunnyCDN
Usage: import and call upload_thumbnail(url_or_path, video_id) -> cdn_url or None
"""
import os
import re
import logging
import requests

BUNNY_STORAGE_ZONE = 'clankervids'
BUNNY_ACCESS_KEY   = '9935b528-3e77-488d-9508b6340d99-1972-48bd'
BUNNY_STORAGE_URL  = f'https://storage.bunnycdn.com/{BUNNY_STORAGE_ZONE}'
BUNNY_CDN_URL      = 'https://clankervids-cdn.b-cdn.net'

HEADERS = {'AccessKey': BUNNY_ACCESS_KEY, 'Content-Type': 'application/octet-stream'}
log = logging.getLogger('bunny_thumb')

# Minimal browser-like headers to fetch external thumbnails
FETCH_HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'image/webp,image/jpeg,image/*',
}


def _cdn_url(video_id: str) -> str:
    return f'{BUNNY_CDN_URL}/thumbnails/{video_id}.jpg'


def already_on_cdn(thumbnail_url: str) -> bool:
    return thumbnail_url and 'b-cdn.net' in thumbnail_url


def upload_thumbnail(source_url: str, video_id: str, timeout: int = 10) -> str | None:
    """
    Download thumbnail from source_url and upload to Bunny CDN.
    Returns the CDN URL on success, None on failure.
    """
    if not source_url:
        return None
    if already_on_cdn(source_url):
        return source_url

    try:
        r = requests.get(source_url, headers=FETCH_HEADERS, timeout=timeout)
        r.raise_for_status()
        data = r.content
    except Exception as e:
        log.warning(f'Failed to fetch thumbnail {source_url}: {e}')
        return None

    remote_path = f'thumbnails/{video_id}.jpg'
    try:
        resp = requests.put(
            f'{BUNNY_STORAGE_URL}/{remote_path}',
            headers=HEADERS,
            data=data,
            timeout=30,
        )
        if resp.status_code in (200, 201):
            return _cdn_url(video_id)
        else:
            log.warning(f'Bunny upload failed {resp.status_code}: {resp.text[:100]}')
            return None
    except Exception as e:
        log.warning(f'Bunny upload exception: {e}')
        return None
