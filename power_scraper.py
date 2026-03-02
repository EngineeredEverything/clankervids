#!/usr/bin/env python3
"""
ClankerVids Power Scraper v2.0
Multi-source viral robot content engine.

Sources:
  1. Reddit (enhanced) - hot/new/rising across 30+ subs
  2. YouTube Search (yt-dlp, no API key) - 30 keyword searches
  3. YouTube Channels (yt-dlp) - monitor top robot channels
  4. Velocity scoring - prioritize content gaining views fast

Run modes:
  python3 power_scraper.py full     -- full scan all sources (~5-10 min)
  python3 power_scraper.py quick    -- fast scan hot/new only (~1-2 min)
  python3 power_scraper.py youtube  -- YouTube only
  python3 power_scraper.py reddit   -- Reddit only
  python3 power_scraper.py stats    -- show DB stats
"""

import os, re, json, time, sqlite3, uuid, sys, subprocess, logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

DB_PATH = '/var/www/clankervids/clankervids.db'
LOG_PATH = '/var/log/power_scraper.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────

REDDIT_HEADERS = {'User-Agent': 'ClankerVids/3.0 (robot content aggregator)'}

CORE_SUBS = [
    'shittyrobots', 'robotics', 'Battlebots', 'BostonDynamics', 'MechanicalGifs',
    'HumanoidRobots', 'drones', 'fpv', 'Multicopter', 'diydrones',
    'autonomousvehicles', 'SelfDrivingCars', 'unitree', 'RobotDogs',
]

GENERAL_SUBS = [
    'singularity', 'ArtificialIntelligence', 'MachineLearning', 'artificial',
    'Futurology', 'interestingasfuck', 'nextfuckinglevel', 'Damnthatsinteresting',
    'Whatcouldgowrong', 'oddlysatisfying', 'technology', 'EngineeringPorn',
    'videos', 'gifs', 'geek', 'cyberpunk', 'ScienceAndTechnology', 'funny',
    'specializedtools', 'ChatGPT', 'OpenAI',
]

ALWAYS_QUALIFY = {s.lower() for s in CORE_SUBS}

YT_SEARCHES = [
    'humanoid robot 2025 2026',
    'Figure AI robot demo',
    'Tesla Optimus robot walking',
    'Boston Dynamics Atlas parkour',
    '1X robot NEO',
    'Agility Robotics Digit',
    'Apptronik Apollo robot',
    'Unitree H1 humanoid',
    'humanoid robot fail compilation',
    'FPV drone crash compilation 2025',
    'drone fail funny',
    'drone racing crash gopro',
    'DJI drone fail',
    'robot dog fail compilation',
    'Boston Dynamics Spot fail',
    'Unitree Go2 robot dog',
    'AI robot going wrong 2025',
    'robot malfunction fail compilation',
    'warehouse robot fail',
    'BattleBots fight 2025',
    'robot battle compilation',
    'viral robot video 2025',
    'robot bloopers fails compilation',
    'amazing robot technology 2025',
    'robot highlight reel',
    'drone swarm light show',
    'robot arm precision',
    'industrial robot accident fail',
    'self driving car fail',
    'robot surgery malfunction',
]

YT_CHANNELS = [
    'https://www.youtube.com/@BostonDynamics/videos',
    'https://www.youtube.com/@FigureAI/videos',
    'https://www.youtube.com/@UnitreeRobotics/videos',
    'https://www.youtube.com/@AgilityRobotics/videos',
    'https://www.youtube.com/@1XTechnologies/videos',
    'https://www.youtube.com/@Apptronik/videos',
]

ROBOT_KW_SUB = [
    'robot', 'robotic', 'humanoid', 'droid', 'battlebots', 'battlebot',
    'boston dynamics', 'tesla bot', 'tesla optimus', 'unitree', 'agility robotics',
    '1x technologies', 'figure robot', 'ameca', 'sanctuary ai',
    'quadruped', 'exoskeleton', 'bionic', 'cyborg', 'robot arm', 'robot dog',
    'robot hand', 'warehouse robot', 'delivery robot', 'surgical robot',
    'industrial robot', 'cobots', 'cobot', 'quadcopter', 'multicopter', 'uav',
    'unmanned aerial', 'drone swarm', 'drone show', 'drone fail',
    'artificial intelligence', 'machine learning', 'self-driving', 'automation',
    'automated', 'servo', 'actuator',
]

ROBOT_KW_EXACT = [
    'ai', 'drone', 'drones', 'gpt', 'neural', 'android',
    'autonomous', 'mechanical', 'fpv', 'uav',
]

FAIL_KW = [
    'fail', 'fails', 'falling', 'crash', 'crashed', 'oops', 'malfunction',
    'broken', 'glitch', 'shitty', 'disaster', 'explosion', 'explode',
    'breakdown', 'error', 'gone wrong', 'dropped', 'tipped', 'fell',
    'stumble', 'bloopers', 'blooper', 'accident',
]

BATTLE_KW = [
    'battle', 'fight', 'vs ', ' vs', 'combat', 'destroy', 'battlebots',
    'combat robot', 'robot war',
]


# ── DB helpers ──────────────────────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def video_exists(video_url, youtube_id=None, title=None):
    try:
        conn = get_conn()
        c = conn.cursor()
        if youtube_id:
            c.execute("SELECT 1 FROM videos WHERE youtube_id=?", (youtube_id,))
            if c.fetchone():
                conn.close()
                return True
        c.execute("SELECT 1 FROM videos WHERE video_url=?", (video_url,))
        if c.fetchone():
            conn.close()
            return True
        if title:
            pfx = title[:50].lower().strip()
            c.execute("SELECT 1 FROM videos WHERE LOWER(SUBSTR(title,1,50))=?", (pfx,))
            if c.fetchone():
                conn.close()
                return True
        conn.close()
        return False
    except Exception:
        return False


def insert_video(title, description, creator, category, video_url, thumbnail_url,
                 youtube_id=None, view_count=0, score=0):
    try:
        conn = get_conn()
        c = conn.cursor()
        vid_id = str(uuid.uuid4())
        # Upload thumbnail to Bunny CDN for fast delivery
        try:
            sys.path.insert(0, '/var/www/clankervids')
            from bunny_thumb import upload_thumbnail
            cdn_url = upload_thumbnail(thumbnail_url, vid_id)
            if cdn_url:
                thumbnail_url = cdn_url
        except Exception:
            pass
        c.execute(
            '''INSERT INTO videos
               (id, title, description, creator, category, created_at, views,
                clanks, epic_bots, system_errors, comments, shares,
                thumbnail_url, video_url, status, duration, youtube_id,
                view_count, upload_date)
               VALUES (?,?,?,?,?,?,?,0,0,0,0,0,?,?,'active',30,?,?,?)''',
            (
                vid_id, title[:200], description[:300], creator[:100], category,
                datetime.now().isoformat(), max(score, view_count),
                thumbnail_url, video_url, youtube_id,
                view_count, datetime.now().isoformat()
            )
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        log.error(f"DB insert error: {e}")
        return False


# ── Content classifiers ─────────────────────────────────────────────────────

def is_robot_content(title, subreddit=''):
    if subreddit.lower() in ALWAYS_QUALIFY:
        return True
    t = title.lower()
    if any(kw in t for kw in ROBOT_KW_SUB):
        return True
    for kw in ROBOT_KW_EXACT:
        if re.search(r'\b' + re.escape(kw) + r'\b', t):
            return True
    return False


def categorize(title, subreddit=''):
    t = title.lower()
    sub = subreddit.lower()
    if sub in ('shittyrobots', 'whatcouldgowrong') or any(kw in t for kw in FAIL_KW):
        return 'fails'
    if sub == 'battlebots' or any(kw in t for kw in BATTLE_KW):
        return 'battles'
    return 'highlights'


def extract_youtube_id(url):
    for pat in [
        r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
    ]:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def best_thumbnail(yt_id):
    for res in ['maxresdefault', 'sddefault', 'hqdefault']:
        url = f"https://i.ytimg.com/vi/{yt_id}/{res}.jpg"
        try:
            r = requests.head(url, timeout=5)
            if r.status_code == 200 and int(r.headers.get('Content-Length', 0)) > 5000:
                return url
        except Exception:
            pass
    return f"https://i.ytimg.com/vi/{yt_id}/hqdefault.jpg"


# ── Reddit scraper ───────────────────────────────────────────────────────────

def fetch_reddit(subreddit, sort='hot', time_filter='week', limit=25):
    try:
        url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}&t={time_filter}"
        r = requests.get(url, headers=REDDIT_HEADERS, timeout=10)
        if r.status_code != 200:
            log.warning(f"Reddit r/{subreddit} {sort}: {r.status_code}")
            return []
        return [p['data'] for p in r.json().get('data', {}).get('children', [])]
    except Exception as e:
        log.warning(f"Reddit r/{subreddit}: {e}")
        return []


def process_reddit_post(post):
    title = post.get('title', '')
    url = post.get('url', '')
    subreddit = post.get('subreddit', '')
    score = post.get('score', 0)
    author = post.get('author', 'unknown')

    if not is_robot_content(title, subreddit):
        return False

    yt_id = extract_youtube_id(url)

    if video_exists(url, youtube_id=yt_id, title=title):
        return False

    if yt_id:
        video_url = f"https://www.youtube.com/watch?v={yt_id}"
        thumbnail = best_thumbnail(yt_id)
    elif 'v.redd.it' in url or post.get('is_video'):
        media = post.get('media', {}) or {}
        rv = media.get('reddit_video', {})
        raw_url = rv.get('fallback_url', rv.get('dash_url', url))
        import re as _re
        m = _re.match(r'(https://v\.redd\.it/[^/?]+)', raw_url)
        video_url = m.group(1) if m else raw_url
        preview = post.get('preview', {})
        imgs = preview.get('images', [{}])
        thumbnail = (imgs[0].get('source', {}).get('url', '').replace('&amp;', '&')
                     if imgs else post.get('thumbnail', ''))
    else:
        return False

    if not thumbnail or not thumbnail.startswith('http'):
        thumbnail = ''

    cat = categorize(title, subreddit)
    desc = f"From r/{subreddit} - {score:,} upvotes"

    ok = insert_video(title, desc, f"@{author}", cat, video_url, thumbnail,
                      youtube_id=yt_id, score=score)
    if ok:
        log.info(f"[Reddit][{cat}] {title[:65]} (r/{subreddit}, {score:,})")
    return ok


def scan_sub(sub, sort, tf, limit):
    count = 0
    posts = fetch_reddit(sub, sort, tf, limit)
    for p in posts:
        if process_reddit_post(p):
            count += 1
    time.sleep(0.7)
    return count


def scrape_reddit(quick=False):
    added = 0
    limit = 15 if quick else 30
    all_subs = CORE_SUBS + ([] if quick else GENERAL_SUBS)
    sorts = [('hot', 'all')] if quick else [
        ('hot', 'all'), ('top', 'week'), ('new', 'all'), ('rising', 'all')
    ]

    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = []
        for sub in all_subs:
            for sort, tf in sorts:
                futures.append(ex.submit(scan_sub, sub, sort, tf, limit))
        for f in as_completed(futures):
            try:
                added += f.result()
            except Exception:
                pass

    log.info(f"Reddit total added: {added}")
    return added


# ── YouTube scraper via yt-dlp ───────────────────────────────────────────────

def ytdlp_search(query, max_results=15):
    try:
        cmd = [
            'yt-dlp', '--dump-json', '--no-warnings', '--quiet',
            '--flat-playlist', f'ytsearch{max_results}:{query}',
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        items = []
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                pass
        return items
    except Exception as e:
        log.warning(f"yt-dlp search '{query}': {e}")
        return []


def ytdlp_channel(channel_url, max_results=20):
    try:
        cmd = [
            'yt-dlp', '--dump-json', '--no-warnings', '--quiet',
            '--flat-playlist', '--playlist-end', str(max_results),
            channel_url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        items = []
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                pass
        return items
    except Exception as e:
        log.warning(f"yt-dlp channel {channel_url}: {e}")
        return []


def process_yt_item(item, source_query='', force_category=None):
    try:
        yt_id = item.get('id') or ''
        if not yt_id or len(yt_id) != 11:
            return False

        title = item.get('title', '') or item.get('fulltitle', '')
        if not title:
            return False

        video_url = f"https://www.youtube.com/watch?v={yt_id}"

        if video_exists(video_url, youtube_id=yt_id, title=title):
            return False

        if not is_robot_content(title):
            return False

        view_count = int(item.get('view_count') or item.get('views') or 0)
        uploader = item.get('uploader') or item.get('channel') or 'YouTube'

        thumbnail = best_thumbnail(yt_id)
        cat = force_category or categorize(title)

        views_str = f"{view_count:,}" if view_count else 'N/A'
        desc = f"YouTube - {views_str} views"
        if source_query:
            desc += f" - {source_query}"

        ok = insert_video(title, desc, f"@{uploader}", cat, video_url, thumbnail,
                          youtube_id=yt_id, view_count=view_count)
        if ok:
            log.info(f"[YouTube][{cat}] {title[:65]} ({views_str} views)")
        return ok
    except Exception as e:
        log.warning(f"yt process error: {e}")
        return False


def scrape_youtube(quick=False):
    added = 0
    searches = YT_SEARCHES[:10] if quick else YT_SEARCHES
    max_per = 8 if quick else 15

    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(ytdlp_search, q, max_per): q for q in searches}
        for f in as_completed(futures):
            q = futures[f]
            for item in f.result():
                if process_yt_item(item, source_query=q):
                    added += 1

    if not quick:
        for ch_url in YT_CHANNELS:
            log.info(f"Scanning channel: {ch_url}")
            items = ytdlp_channel(ch_url, 15)
            for item in items:
                if process_yt_item(item, force_category='highlights'):
                    added += 1
            time.sleep(2)

    log.info(f"YouTube total added: {added}")
    return added


# ── Stats ────────────────────────────────────────────────────────────────────

def show_stats():
    conn = get_conn()
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM videos WHERE status='active'").fetchone()[0]
    cats = c.execute(
        "SELECT category, COUNT(*) FROM videos WHERE status='active' GROUP BY category"
    ).fetchall()
    recent = c.execute(
        "SELECT title, category, created_at FROM videos ORDER BY created_at DESC LIMIT 8"
    ).fetchall()
    conn.close()

    print(f"\n=== ClankerVids DB Stats ===")
    print(f"Total active: {total}")
    for row in cats:
        print(f"  {row[0]}: {row[1]}")
    print(f"\nRecent additions:")
    for row in recent:
        print(f"  [{row[1]}] {row[0][:70]}")
    print()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'full'
    start = time.time()
    total = 0

    log.info(f"=== Power Scraper starting mode={mode} ===")

    if mode == 'full':
        total += scrape_reddit(quick=False)
        total += scrape_youtube(quick=False)
    elif mode == 'quick':
        total += scrape_reddit(quick=True)
        total += scrape_youtube(quick=True)
    elif mode == 'reddit':
        total += scrape_reddit(quick=False)
    elif mode == 'youtube':
        total += scrape_youtube(quick=False)
    elif mode == 'stats':
        show_stats()
        return

    elapsed = round(time.time() - start, 1)
    log.info(f"=== Done in {elapsed}s — added {total} videos ===")
    show_stats()


if __name__ == '__main__':
    main()
