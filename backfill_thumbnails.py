#!/usr/bin/env python3
"""
Backfill existing video thumbnails to Bunny CDN.
Run once: python3 backfill_thumbnails.py
"""
import sys, sqlite3, time, logging
sys.path.insert(0, '/var/www/clankervids')
from bunny_thumb import upload_thumbnail, already_on_cdn

DB = '/var/www/clankervids/clankervids.db'
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger('backfill')

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""
    SELECT id, thumbnail_url FROM videos
    WHERE status='active'
    AND thumbnail_url IS NOT NULL AND thumbnail_url != ''
    AND thumbnail_url NOT LIKE '%b-cdn.net%'
    ORDER BY created_at DESC
""")
rows = cur.fetchall()
log.info(f"Thumbnails to backfill: {len(rows)}")

ok = fail = skip = 0
for i, row in enumerate(rows):
    vid_id = row['id']
    src = row['thumbnail_url']

    cdn_url = upload_thumbnail(src, vid_id, timeout=15)
    if cdn_url:
        conn.execute('UPDATE videos SET thumbnail_url=? WHERE id=?', (cdn_url, vid_id))
        if i % 25 == 0:
            conn.commit()
        ok += 1
    else:
        fail += 1

    if (i + 1) % 50 == 0:
        log.info(f"  Progress: {i+1}/{len(rows)} — ok={ok} fail={fail}")

    time.sleep(0.05)  # gentle rate limit

conn.commit()
conn.close()
log.info(f"Done — uploaded={ok} failed={fail}")
