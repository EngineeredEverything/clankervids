#!/usr/bin/env python3
"""
ClankerVids Reddit Content Curator
Pulls viral robot content from Reddit - no YouTube auth needed!
"""

import os
import re
import json
import time
import sqlite3
import requests
import uuid
from datetime import datetime
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/reddit_curator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class RedditCurator:
    def __init__(self):
        self.db_path = '/var/www/clankervids/clankervids.db'
        self.headers = {'User-Agent': 'ClankerVids/2.0 (robot content aggregator)'}
        
        # Robot-focused subreddits
        self.subreddits = [
            'shittyrobots',           # Classic robot fails
            'robotics',               # Serious robotics
            'Battlebots',             # Robot battles
            'BostonDynamics',         # Boston Dynamics content
            'MachineLearning',        # AI/ML
            'artificial',             # Artificial intelligence
            'Futurology',             # Tech future
            'interestingasfuck',      # Viral content (filter for robots)
            'nextfuckinglevel',        # Amazing tech (filter for robots)
            'Damnthatsinteresting',   # Viral wow-factor (filter for robots)
            'funny',                  # Viral funny (filter for robots)
            'technology',             # Tech news
            'EngineeringPorn',        # Cool engineering
            'MechanicalGifs',         # Mechanical content
            'videos',                 # General videos (robot/AI filtered)
            'gifs',                   # GIFs (robot filtered)
            'geek',                   # Geek content (robot filtered)
            'cyberpunk',              # Futuristic tech (robot filtered)
            'ScienceAndTechnology',   # Science & tech news
        ]
        
        # Keywords that make something robot-related (substring match is safe)
        self.robot_keywords_substring = [
            'robot', 'robotic', 'humanoid', 'droid',
            'boston dynamics', 'tesla bot',
            'unitree', 'quadruped',
            'artificial intelligence', 'machine learning',
            'self-driving', 'automation', 'automated',
            'servo', 'actuator', 'cyborg',
            'chatgpt', 'exoskeleton', 'bionic',
            'battlebots', 'battlebot',
        ]
        
        # Keywords that need word-boundary matching (too generic as substrings)
        self.robot_keywords_exact = [
            'ai', 'drone', 'drones', 'gpt', 'neural', 'android',
            'autonomous', 'mechanical',
        ]
        
        # Brand/product names that are too ambiguous alone — require a second
        # robot-related word nearby to count (e.g. "atlas robot" yes, "atlas mountains" no)
        self.contextual_keywords = ['atlas', 'spot', 'optimus', 'figure', 'digit']
        self.context_helpers = [
            'robot', 'humanoid', 'boston dynamics', 'unitree', 'tesla',
            'walking', 'bipedal', 'legged', 'autonomous',
        ]
        
        # Fail keywords for categorization
        self.fail_keywords = ['fail', 'fails', 'falling', 'crash', 'oops', 'malfunction', 'broken', 'glitch', 'shitty']
        self.battle_keywords = ['battle', 'fight', 'vs', 'combat', 'destroy', 'battlebots']
        
    def is_robot_content(self, title: str, subreddit: str) -> bool:
        """Check if content is robot-related"""
        # Robot-specific subreddits always qualify
        robot_subs = ['shittyrobots', 'robotics', 'battlebots', 'bostondynamics', 'machinelearning', 'artificial']
        if subreddit.lower() in robot_subs:
            return True
        
        title_lower = title.lower()
        
        # Substring match for unambiguous keywords
        if any(kw in title_lower for kw in self.robot_keywords_substring):
            return True
        
        # Word-boundary match for ambiguous keywords (prevents "spotted" matching "spot", etc.)
        for kw in self.robot_keywords_exact:
            if re.search(r'\b' + re.escape(kw) + r'\b', title_lower):
                return True
        
        # Contextual keywords — only match if a helper word is also present
        for kw in self.contextual_keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', title_lower):
                if any(h in title_lower for h in self.context_helpers):
                    return True
        
        return False
    
    def categorize(self, title: str, subreddit: str) -> str:
        """Categorize the video"""
        title_lower = title.lower()
        sub_lower = subreddit.lower()
        
        if sub_lower == 'shittyrobots' or any(kw in title_lower for kw in self.fail_keywords):
            return 'fails'
        elif sub_lower == 'battlebots' or any(kw in title_lower for kw in self.battle_keywords):
            return 'battles'
        else:
            return 'highlights'
    
    def extract_youtube_id(self, url: str) -> str:
        """Extract YouTube video ID from URL"""
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def video_exists(self, video_url: str, youtube_id: str = None, title: str = None) -> bool:
        """Check if video already exists by youtube_id, URL, or similar title"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check youtube_id first (most reliable for YouTube videos)
            if youtube_id:
                cursor.execute("SELECT 1 FROM videos WHERE youtube_id = ?", (youtube_id,))
                if cursor.fetchone():
                    conn.close()
                    return True
            
            # Check exact URL match
            cursor.execute("SELECT 1 FROM videos WHERE video_url = ?", (video_url,))
            if cursor.fetchone():
                conn.close()
                return True
            
            # Check for very similar titles (first 50 chars) to catch edge cases
            if title:
                title_prefix = title[:50].lower().strip()
                cursor.execute("SELECT 1 FROM videos WHERE LOWER(SUBSTR(title, 1, 50)) = ?", (title_prefix,))
                if cursor.fetchone():
                    conn.close()
                    return True
            
            conn.close()
            return False
        except:
            return False
    
    def add_video(self, post: dict) -> bool:
        """Add a video from Reddit post data"""
        try:
            title = post.get('title', 'Untitled')
            url = post.get('url', '')
            subreddit = post.get('subreddit', '')
            score = post.get('score', 0)
            author = post.get('author', 'unknown')
            
            # Skip if not robot content
            if not self.is_robot_content(title, subreddit):
                return False
            
            # Determine video URL and thumbnail
            youtube_id = self.extract_youtube_id(url)
            
            # Skip if already exists (check youtube_id, url, and title)
            if self.video_exists(url, youtube_id=youtube_id, title=title):
                logger.info(f"Skipped (exists): {title[:50]}")
                return False
            
            if youtube_id:
                video_url = f"https://www.youtube.com/watch?v={youtube_id}"
                thumbnail_url = f"https://i.ytimg.com/vi/{youtube_id}/hqdefault.jpg"
            elif 'v.redd.it' in url:
                video_url = url
                # Reddit videos - use preview image if available
                preview = post.get('preview', {})
                images = preview.get('images', [{}])
                thumbnail_url = images[0].get('source', {}).get('url', '').replace('&amp;', '&') if images else ''
                if not thumbnail_url:
                    thumbnail_url = post.get('thumbnail', '')
            elif post.get('is_video'):
                media = post.get('media', {}) or {}
                reddit_video = media.get('reddit_video', {})
                video_url = reddit_video.get('fallback_url', url)
                thumbnail_url = post.get('thumbnail', '')
            else:
                # Not a video we can use
                return False
            
            # Clean up thumbnail URL
            if thumbnail_url and thumbnail_url.startswith('http'):
                thumbnail_url = thumbnail_url.replace('&amp;', '&')
            else:
                thumbnail_url = ''
            
            category = self.categorize(title, subreddit)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            video_id = str(uuid.uuid4())
            
            cursor.execute('''
                INSERT INTO videos (
                    id, title, description, creator, category,
                    created_at, views, clanks, epic_bots, system_errors,
                    comments, shares, thumbnail_url, video_url, status,
                    duration, youtube_id, view_count, upload_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, ?, ?, 'active', ?, ?, ?, ?)
            ''', (
                video_id,
                title[:200],
                f"From r/{subreddit} • {score:,} upvotes",
                f"@{author}",
                category,
                datetime.now().isoformat(),
                score,  # Use Reddit score as initial "views"
                thumbnail_url,
                video_url,
                30.0,  # Default duration
                youtube_id,
                score,
                datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Added: {title[:50]}... [{category}] ({score:,} upvotes) from r/{subreddit}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding video: {e}")
            return False
    
    def fetch_subreddit(self, subreddit: str, sort: str = 'top', time_filter: str = 'month', limit: int = 25) -> list:
        """Fetch posts from a subreddit"""
        try:
            url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}&t={time_filter}"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch r/{subreddit}: {response.status_code}")
                return []
            
            data = response.json()
            posts = data.get('data', {}).get('children', [])
            
            return [post['data'] for post in posts]
            
        except Exception as e:
            logger.error(f"Error fetching r/{subreddit}: {e}")
            return []
    
    def run_scan(self, limit_per_sub: int = 30) -> int:
        """Run a full Reddit scan"""
        logger.info("🤖 Starting Reddit robot content scan...")
        added = 0
        
        for subreddit in self.subreddits:
            logger.info(f"Scanning r/{subreddit}...")
            
            # Get top posts from this month
            posts = self.fetch_subreddit(subreddit, 'top', 'month', limit_per_sub)
            
            for post in posts:
                if self.add_video(post):
                    added += 1
            
            # Also get hot posts
            posts = self.fetch_subreddit(subreddit, 'hot', 'all', limit_per_sub // 2)
            
            for post in posts:
                if self.add_video(post):
                    added += 1
            
            time.sleep(1)  # Rate limiting
        
        logger.info(f"🎬 Reddit scan complete. Added {added} new videos.")
        return added
    
    def quick_stats(self):
        """Show current video stats"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT category, COUNT(*) FROM videos WHERE status='active' GROUP BY category")
            stats = cursor.fetchall()
            total = sum(s[1] for s in stats)
            conn.close()
            
            print(f"\n📊 ClankerVids Stats:")
            print(f"   Total videos: {total}")
            for cat, count in stats:
                print(f"   {cat}: {count}")
            print()
            
        except Exception as e:
            print(f"Error: {e}")

def main():
    import sys
    
    curator = RedditCurator()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == 'scan':
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            added = curator.run_scan(limit)
            print(f"\n✅ Added {added} new videos!")
            curator.quick_stats()
        elif sys.argv[1] == 'stats':
            curator.quick_stats()
        else:
            print("Usage:")
            print("  python reddit_curator.py scan [limit]  - Scan Reddit for robot content")
            print("  python reddit_curator.py stats         - Show current stats")
    else:
        curator.run_scan()
        curator.quick_stats()

if __name__ == '__main__':
    main()
