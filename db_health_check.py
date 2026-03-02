#!/usr/bin/env python3
"""
ClankerVids DB Health Check
Runs periodically to catch and fix common data quality issues:
  1. Reddit CMAF URLs stored with suffix instead of clean base URL
  2. Videos with null/empty video_url
  3. Videos with null/empty thumbnail_url that could have one derived
"""

import sqlite3
import re
import logging
from datetime import datetime

DB = '/var/www/clankervids/clankervids.db'
LOG = '/var/log/clankervids_db_health.log'

logging.basicConfig(
    filename=LOG,
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
log = logging.getLogger('db_health')


def fix_reddit_cmaf_urls(cur):
    """Strip CMAF/fallback suffix from Reddit video URLs."""
    cur.execute(
        "SELECT id, video_url FROM videos "
        "WHERE video_url LIKE 'https://v.redd.it/%' "
        "AND (video_url LIKE '%CMAF%' OR video_url LIKE '%fallback%' OR video_url LIKE '%dash%')"
    )
    rows = cur.fetchall()
    fixed = 0
    for vid_id, url in rows:
        m = re.match(r'(https://v\.redd\.it/[^/?]+)', url)
        if m and m.group(1) != url:
            cur.execute('UPDATE videos SET video_url=? WHERE id=?', (m.group(1), vid_id))
            fixed += 1
    return fixed


def derive_missing_youtube_thumbnails(cur):
    """For YouTube videos missing thumbnails, derive from youtube_id."""
    cur.execute(
        "SELECT id, youtube_id FROM videos "
        "WHERE (thumbnail_url IS NULL OR thumbnail_url = '') "
        "AND youtube_id IS NOT NULL AND youtube_id != '' "
        "AND status = 'active'"
    )
    rows = cur.fetchall()
    fixed = 0
    for vid_id, yt_id in rows:
        thumb = f"https://i.ytimg.com/vi/{yt_id}/hqdefault.jpg"
        cur.execute('UPDATE videos SET thumbnail_url=? WHERE id=?', (thumb, vid_id))
        fixed += 1
    return fixed


def flag_broken_videos(cur):
    """Count videos with no playable URL."""
    cur.execute(
        "SELECT COUNT(*) FROM videos "
        "WHERE (video_url IS NULL OR video_url = '') AND status = 'active'"
    )
    count = cur.fetchone()[0]
    return count


def main():
    log.info("=== DB health check started ===")
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    r1 = fix_reddit_cmaf_urls(cur)
    r2 = derive_missing_youtube_thumbnails(cur)
    r3 = flag_broken_videos(cur)

    conn.commit()
    conn.close()

    log.info(f"Reddit CMAF URLs fixed: {r1}")
    log.info(f"YouTube thumbnails derived: {r2}")
    log.info(f"Videos with no URL (active): {r3}")
    log.info("=== DB health check done ===")

    if r1 or r2:
        print(f"[db_health] Fixed {r1} Reddit URLs, {r2} YouTube thumbnails, {r3} broken video URLs")
    else:
        print(f"[db_health] All clean. Broken video URLs (active): {r3}")


if __name__ == '__main__':
    main()
