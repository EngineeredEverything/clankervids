#!/usr/bin/env python3
"""
ClankerVids Daily Robot Digest
Generates an AI-narrated audio roundup of the top robot videos of the day.
Powered by ElevenLabs.
"""

import os
import sqlite3
import json
import requests
from datetime import datetime, timedelta
import sys

DATABASE_PATH = '/var/www/clankervids/clankervids.db'
OUTPUT_DIR = '/var/www/clankervids/public'
OUTPUT_PATH = '/var/www/clankervids/public/daily_digest.mp3'
DIGEST_META_PATH = '/var/www/clankervids/public/daily_digest.json'

ELEVENLABS_API_KEY = os.environ.get('ELEVENLABS_API_KEY', '')
VOICE_ID = 'IKne3meq5aSn9XLyUdCD'  # Charlie - Deep, Confident, Energetic
MODEL_ID = 'eleven_multilingual_v2'  # Higher quality

def get_top_videos(limit=5):
    """Fetch top videos by engagement from the last 30 days."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row

    # Get most-viewed videos overall (site is young, so not filtering by date too strictly)
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()

    cursor = conn.execute("""
        SELECT id, title, description, category, views, clanks, system_errors, youtube_id, created_at
        FROM videos
        WHERE status = 'active'
        ORDER BY (COALESCE(views, 0) + COALESCE(clanks, 0) * 10 + COALESCE(system_errors, 0) * 5) DESC
        LIMIT ?
    """, (limit,))

    videos = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return videos


def get_category_counts():
    """Get video counts by category."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.execute("""
        SELECT category, COUNT(*) as count
        FROM videos WHERE status = 'active'
        GROUP BY category
    """)
    counts = {row[0]: row[1] for row in cursor.fetchall()}
    total = sum(counts.values())
    conn.close()
    return counts, total


def clean_title(title):
    """Clean up a video title for speech."""
    # Remove common clickbait elements, pipe chars, excessive caps
    title = title.replace('|', ' — ')
    title = title.replace('&amp;', 'and')
    title = title.replace('  ', ' ')
    # Trim at 80 chars if too long
    if len(title) > 80:
        title = title[:77] + '...'
    return title.strip()


def write_digest_script(videos, category_counts, total_videos):
    """Write a punchy, engaging digest script."""
    today = datetime.now().strftime('%A, %B %d')
    
    # Category-specific flavor
    category_icons = {
        'highlights': 'highlight reel',
        'fails': 'robot fail',
        'battles': 'battle'
    }

    # Opening hook
    script = f"What's up, it's your Daily Robot Digest for {today}. "
    script += f"ClankerVids is running {total_videos} robot videos across {len(category_counts)} categories. "
    
    # Quick category breakdown
    cats = []
    if category_counts.get('highlights'):
        cats.append(f"{category_counts['highlights']} highlights")
    if category_counts.get('fails'):
        cats.append(f"{category_counts['fails']} fails")
    if category_counts.get('battles'):
        cats.append(f"{category_counts['battles']} battles")
    
    if cats:
        script += f"We've got " + ", ".join(cats) + ". "
    
    script += "Here are the top picks right now. "
    
    # Top videos
    for i, video in enumerate(videos[:5], 1):
        title = clean_title(video['title'])
        category = video.get('category', 'highlights')
        cat_label = category_icons.get(category, 'video')
        
        if i == 1:
            script += f"Number one: '{title}'. "
            if video.get('views', 0) > 100000:
                views_m = video['views'] / 1_000_000
                script += f"Over {views_m:.1f} million views — this one's a monster. "
            else:
                script += f"A crowd favorite in the {cat_label} category. "
        elif i == 2:
            script += f"Coming in at number two: '{title}'. "
            if category == 'fails':
                script += "Classic robot fail energy. "
            elif category == 'battles':
                script += "The battles category never disappoints. "
            else:
                script += "Pure robotic excellence. "
        elif i == 3:
            script += f"Third pick: '{title}'. "
        elif i == 4:
            script += f"Also trending: '{title}'. "
        elif i == 5:
            script += f"And rounding out the top five: '{title}'. "
    
    # Closer
    script += "That's your robot digest. "
    script += "Hit up ClankerVids dot com for the full feed — updated every six hours with fresh content. "
    script += "Stay clunky out there."
    
    return script


def generate_audio(script_text):
    """Generate audio from text using ElevenLabs."""
    if not ELEVENLABS_API_KEY:
        print("ERROR: ELEVENLABS_API_KEY not set")
        return False
    
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "text": script_text,
        "model_id": MODEL_ID,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.2,
            "use_speaker_boost": True
        }
    }
    
    print(f"Generating audio ({len(script_text)} chars)...")
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    
    if response.status_code == 200:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(OUTPUT_PATH, 'wb') as f:
            f.write(response.content)
        print(f"Audio saved: {OUTPUT_PATH} ({len(response.content):,} bytes)")
        return True
    else:
        print(f"ElevenLabs error {response.status_code}: {response.text[:200]}")
        return False


def save_digest_metadata(videos, script_text):
    """Save digest metadata for the frontend."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    meta = {
        "generated_at": datetime.now().isoformat(),
        "date": datetime.now().strftime('%A, %B %d, %Y'),
        "script": script_text,
        "top_videos": [
            {
                "id": v['id'],
                "title": clean_title(v['title']),
                "category": v.get('category', 'highlights'),
                "youtube_id": v.get('youtube_id'),
                "views": v.get('views', 0)
            }
            for v in videos[:5]
        ],
        "audio_url": "/public/daily_digest.mp3"
    }
    with open(DIGEST_META_PATH, 'w') as f:
        json.dump(meta, f, indent=2)
    print(f"Metadata saved: {DIGEST_META_PATH}")


def main():
    print(f"\n{'='*50}")
    print(f"ClankerVids Daily Digest Generator")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*50}")

    # Get data
    videos = get_top_videos(5)
    category_counts, total_videos = get_category_counts()
    
    print(f"Found {total_videos} total videos, {len(videos)} top picks")
    
    if not videos:
        print("No videos found — skipping digest generation")
        return 1
    
    # Write script
    script = write_digest_script(videos, category_counts, total_videos)
    print(f"\n--- SCRIPT ---\n{script}\n{'='*50}")
    
    # Save metadata first (so frontend has something even if audio fails)
    save_digest_metadata(videos, script)
    
    # Generate audio
    success = generate_audio(script)
    
    if success:
        print("\n✅ Daily digest generated successfully!")
        return 0
    else:
        print("\n❌ Audio generation failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
