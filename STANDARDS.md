# STANDARDS.md — ClankerVids Development Standards

All code changes to this repo must follow these rules. These exist because
we learned them the hard way. Don't skip them.

---

## 1. Video URLs

### Reddit (`v.redd.it`)
**Always store the clean base URL. Never store the CMAF/fallback/dash suffix.**

```python
# ✅ CORRECT
import re
m = re.match(r'(https://v\.redd\.it/[^/?]+)', raw_url)
video_url = m.group(1) if m else raw_url
# → https://v.redd.it/abc123xyz

# ❌ WRONG — breaks HLS playback on mobile
video_url = reddit_video.get('fallback_url', url)
# → https://v.redd.it/abc123xyz/CMAF_1080.mp4?source=fallback
```

**Why:** The frontend builds `{base}/HLSPlaylist.m3u8` for playback. If the
URL has a suffix, the HLS path is malformed and video won't play on mobile.

### YouTube
Store the full watch URL: `https://www.youtube.com/watch?v={youtube_id}`
Also store `youtube_id` separately — it's used for thumbnail fallbacks.

### Frontend playback
- `v.redd.it` → HLS via `hls.js`, URL = `{base}/HLSPlaylist.m3u8`
- YouTube → `<iframe>` embed
- Other MP4 → native `<video>` tag

---

## 2. Thumbnails

**All thumbnails must go through Bunny CDN. Never store external hotlink URLs directly.**

```python
# ✅ CORRECT — in any scraper, after generating video_id
from bunny_thumb import upload_thumbnail
cdn_url = upload_thumbnail(raw_thumbnail_url, video_id)
if cdn_url:
    thumbnail_url = cdn_url
# Falls back to original URL if Bunny upload fails — that's fine

# ❌ WRONG — direct hotlink to Reddit/YouTube CDN
thumbnail_url = post['preview']['images'][0]['source']['url']
```

**Why:** `external-preview.redd.it` is slow, can 404, and we have no control.
Bunny CDN serves from edge in ~60ms globally. Storage cost is ~$0.01/GB/month.

### Helper module
`/var/www/clankervids/bunny_thumb.py` — use it everywhere.

```python
from bunny_thumb import upload_thumbnail
cdn_url = upload_thumbnail(source_url, video_id)  # returns CDN URL or None
```

### Frontend image tags
- First 4 visible thumbnails: `loading="eager" fetchpriority="high"`
- All others: `loading="lazy"`
- Always include `onerror` fallback (robot placeholder SVG, not `display=none`)

```html
<!-- ✅ Above the fold -->
<img src="${thumb}" loading="eager" fetchpriority="high" onerror="this.src='...placeholder...'">

<!-- ✅ Below the fold -->
<img src="${thumb}" loading="lazy" onerror="this.src='...placeholder...'">

<!-- ❌ Silent failure - shows nothing -->
<img src="${thumb}" onerror="this.style.display='none'">
```

---

## 3. Deduplication

Any code that inserts videos must call `video_exists()` (curator) or equivalent
before inserting. The check must cover:

1. `youtube_id` match (most reliable)
2. Exact `video_url` match
3. Clean base Reddit URL match (strip CMAF suffix before checking)
4. Title prefix match — first **60 chars**, lowercased, stripped

```python
# In reddit_curator.py — video_exists() already handles all four checks.
# In power_scraper.py — video_exists() also handles it.
# Any NEW scraper must implement the same four checks.
```

**Never skip the title check.** Reddit reposts the same video with the same
title regularly. The URL changes; the title doesn't.

---

## 4. Content Quality Filters

Any new scraper or subreddit addition must apply these filters:

### Score thresholds by source type
| Source | Minimum Score |
|--------|---------------|
| Hobby/niche subs (fpv, diydrones, multicopter) | 50 |
| Hobby subs with junk keywords | 200 |
| General viral subs (nextfuckinglevel, etc.) | 100 |
| Dedicated robot subs (robotics, shittyrobots, battlebots) | 0 (no floor) |

### Blocked title patterns (hobby subs)
Posts matching these patterns are dropped unless they clear the 200-score bar:
- Help/question signals: `help`, `question`, `pls`, `plz`, `anyone know`
- Hardware jargon (low signal): `esc`, `vtx`, `analog`, `betaflight`, `crossfire`, `elrs`, `lipo`, `props`
- Personal milestones (not shareable): `my first`, `beginner`, `noob`

### Always check `is_robot_content()` first
Before any insert, content must pass the robot relevance check. Adding a new
subreddit to `always_qualify_subs` bypasses keyword filtering — only do this
for subs that are 100% on-topic.

---

## 5. Categorization

Use this decision tree — in order:

```
1. Sub in ('shittyrobots', 'whatcouldgowrong') → 'fails'
   OR title contains fail keywords → 'fails'

2. Sub in ('battlebots', 'robotcombat') → 'battles'
   OR title contains battle keywords → 'battles'

3. Title contains highlight keywords → 'highlights'

4. Sub in ('fpv', 'multicopter', 'diydrones') → 'highlights'

5. Default → 'highlights'
```

**Do not add new categories without updating:**
- `backend/app.py` category filter
- `index.html` category pills + `getCategoryEmoji()`
- This document

---

## 6. API Design

### Pagination — mandatory
The `/api/videos` endpoint is paginated. Any new list endpoint must also paginate.
- Default: 50 per page, max 100
- Query params: `page=1&per_page=50`
- The frontend uses infinite scroll — new list endpoints should follow the same pattern

### Cache headers
Read-only GET endpoints: `Cache-Control: public, max-age=120, s-maxage=120`
Mutation endpoints (POST/react/subscribe): no cache headers (CF won't cache POST anyway)

### Response format
`/api/videos` returns a flat JSON array (not a wrapped object) for backwards
compatibility with the frontend. New endpoints may use `{data: [], total: n}`.

---

## 7. Database

### Schema changes
Always test with `sqlite3 clankervids.db` before deploying. Use `ALTER TABLE`
with `IF NOT EXISTS` or handle migration in `init_db()`.

### Soft deletes only
Never `DELETE` rows. Set `status='deleted'`. The DB health check and dedup
logic depend on seeing all records.

```python
# ✅ Correct
cursor.execute("UPDATE videos SET status='deleted' WHERE id=?", (id,))

# ❌ Wrong
cursor.execute("DELETE FROM videos WHERE id=?", (id,))
```

### Daily health check
`db_health_check.py` runs at 3AM via cron. It auto-fixes:
- Reddit CMAF URLs that slipped through
- Missing YouTube thumbnails (derives from `youtube_id`)
- Logs broken video URL count

If you add a new data integrity rule, add it to `db_health_check.py`.

---

## 8. Cron Jobs

Current cron schedule:
```
0 */6 * * *   auto_curator.sh          # Reddit scraper + sitemap
30 6  * * *   run_daily_digest.sh      # ElevenLabs digest
0  9  * * 1   send_weekly_digest.sh    # Weekly email (inactive)
0  3  * * *   db_health_check.py       # DB integrity check
```

Rules:
- Don't add cron jobs that run more often than every 30 minutes
- Log output to `/var/log/clankervids_*.log`
- Append `|| true` to commands that might fail non-fatally

---

## 9. File Management

The `/var/www/clankervids/` root has accumulated ~30 unused backend files
(`clankervids_cdn_backend.py`, `fix_*.py`, etc.) from prior iterations.
**Do not add more one-off scripts here.** If you write a utility script,
either put it in `scripts/` or delete it after use.

Active backend is: `backend/app.py` (served by systemd `clankervids.service`)
Admin backend: `app.py` (port 8080 admin panel)

---

## 10. Git Workflow

```bash
cd /var/www/clankervids
git add <files>
git commit -m "type: short description

- Detail 1
- Detail 2"
git push origin main
```

Commit message types: `fix`, `feat`, `perf`, `quality`, `refactor`, `docs`

Always push after changes. The GitHub repo is the source of truth.
Latest working commit as of 2026-03-02: `e000fbd`
