#!/usr/bin/env python3
"""
ClankerVids Robot Content Curator
Smart, fast video discovery - embeds only, no downloads needed.
"""

import os
import re
import json
import time
import sqlite3
import hashlib
import subprocess
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
import uuid

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/robot_curator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class RobotCurator:
    def __init__(self):
        self.db_path = '/var/www/clankervids/clankervids.db'
        
        # STRICT robot/AI keywords - must contain at least one
        self.must_have_keywords = [
            'robot', 'robots', 'robotic', 'humanoid',
            'boston dynamics', 'atlas', 'spot', 'optimus',
            'tesla bot', 'figure', 'digit', 'unitree',
            'android', 'automaton', 'mech', 'mechanical',
            'drone', 'drones', 'quadruped', 'bipedal',
            'ai ', ' ai', 'artificial intelligence',
            'machine learning', 'neural network',
            'chatgpt', 'gpt-4', 'claude', 'gemini',
            'autonomous', 'self-driving', 'robodog',
            'exoskeleton', 'cyborg', 'bionic',
            'industrial robot', 'robot arm', 'robotic arm',
            'agility robotics', 'xiaomi cyberone', 'ameca',
            'sophia robot', 'pepper robot', 'asimo'
        ]
        
        # Content type keywords for categorization
        self.fail_keywords = ['fail', 'fails', 'falling', 'crash', 'malfunction', 'error', 'bug', 'glitch', 'broken', 'mistake', 'oops', 'disaster']
        self.epic_keywords = ['amazing', 'incredible', 'insane', 'mind-blowing', 'impressive', 'breakthrough', 'revolutionary', 'wow', 'unbelievable']
        self.battle_keywords = ['battle', 'fight', 'vs', 'competition', 'battlebots', 'combat', 'destroy']
        
        # Exclude keywords - if title contains these, skip
        self.exclude_keywords = [
            'kitten', 'cat', 'dog', 'puppy', 'baby', 
            'cooking', 'recipe', 'makeup', 'fashion',
            'minecraft', 'fortnite', 'gaming walkthrough',
            'music video', 'official video', 'lyric video',
            'unboxing toy', 'kids', 'children'
        ]
        
        # Search queries for YouTube
        self.search_queries = [
            'robot fail compilation 2026',
            'robot malfunction funny',
            'boston dynamics atlas fail',
            'humanoid robot falls',
            'tesla optimus fail',
            'AI robot funny moments',
            'robot arm fails',
            'drone crash compilation',
            'robot dog fail',
            'industrial robot accident',
            'robot battle highlights',
            'battlebots best moments',
            'amazing robot technology',
            'humanoid robot walking',
            'robot breakthrough 2026',
            'figure robot demo',
            'unitree robot',
            'spot robot funny',
            'robot vs human',
            'AI fails compilation'
        ]
        
    def is_robot_content(self, title: str, description: str = '') -> bool:
        """Check if content is actually about robots/AI"""
        text = (title + ' ' + description).lower()
        
        # Must have at least one robot keyword
        has_robot = any(kw in text for kw in self.must_have_keywords)
        
        # Must NOT have exclude keywords
        has_exclude = any(kw in text for kw in self.exclude_keywords)
        
        return has_robot and not has_exclude
    
    def categorize_video(self, title: str) -> str:
        """Categorize video based on title"""
        title_lower = title.lower()
        
        if any(kw in title_lower for kw in self.fail_keywords):
            return 'fails'
        elif any(kw in title_lower for kw in self.battle_keywords):
            return 'battles'
        elif any(kw in title_lower for kw in self.epic_keywords):
            return 'highlights'
        else:
            return 'highlights'  # Default to highlights
    
    def get_video_info(self, url: str) -> Optional[Dict]:
        """Get video metadata using yt-dlp (no download)"""
        try:
            cmd = [
                'yt-dlp',
                '--dump-json',
                '--no-download',
                '--no-playlist',
                '--no-warnings',
                url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                return None
                
            data = json.loads(result.stdout)
            
            return {
                'id': data.get('id'),
                'title': data.get('title', 'Untitled'),
                'description': data.get('description', ''),
                'duration': data.get('duration', 0),
                'view_count': data.get('view_count', 0),
                'like_count': data.get('like_count', 0),
                'thumbnail': data.get('thumbnail', ''),
                'uploader': data.get('uploader', 'Unknown'),
                'upload_date': data.get('upload_date', ''),
                'webpage_url': data.get('webpage_url', url)
            }
            
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return None
    
    def search_youtube(self, query: str, max_results: int = 10) -> List[str]:
        """Search YouTube and return video URLs"""
        try:
            cmd = [
                'yt-dlp',
                f'ytsearch{max_results}:{query}',
                '--get-id',
                '--no-warnings',
                '--flat-playlist'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                logger.error(f"Search failed: {result.stderr}")
                return []
            
            video_ids = result.stdout.strip().split('\n')
            urls = [f'https://www.youtube.com/watch?v={vid}' for vid in video_ids if vid]
            
            return urls
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
    
    def video_exists(self, youtube_id: str) -> bool:
        """Check if video already exists in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM videos WHERE youtube_id = ?", (youtube_id,))
            exists = cursor.fetchone() is not None
            conn.close()
            return exists
        except:
            return False
    
    def add_video(self, video_info: Dict) -> bool:
        """Add video to database"""
        try:
            if not self.is_robot_content(video_info['title'], video_info['description']):
                logger.info(f"Skipped (not robot content): {video_info['title']}")
                return False
            
            youtube_id = video_info['id']
            
            if self.video_exists(youtube_id):
                logger.info(f"Skipped (already exists): {video_info['title']}")
                return False
            
            # Get best thumbnail
            thumbnail_url = f"https://i.ytimg.com/vi/{youtube_id}/maxresdefault.jpg"
            
            # Categorize
            category = self.categorize_video(video_info['title'])
            
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
                video_info['title'][:200],
                video_info['description'][:500] if video_info['description'] else 'Discovered by ClankerVids Bot',
                f"@{video_info['uploader'][:50]}",
                category,
                datetime.now().isoformat(),
                video_info['view_count'],
                thumbnail_url,
                video_info['webpage_url'],
                video_info['duration'],
                youtube_id,
                video_info['view_count'],
                datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Added: {video_info['title'][:60]}... [{category}] ({video_info['view_count']:,} views)")
            return True
            
        except Exception as e:
            logger.error(f"Error adding video: {e}")
            return False
    
    def run_scan(self, max_per_query: int = 5) -> int:
        """Run a full content scan"""
        logger.info("🤖 Starting robot content scan...")
        added = 0
        
        for query in self.search_queries:
            logger.info(f"Searching: {query}")
            
            urls = self.search_youtube(query, max_per_query)
            
            for url in urls:
                video_info = self.get_video_info(url)
                
                if video_info:
                    if self.add_video(video_info):
                        added += 1
                        
                time.sleep(1)  # Rate limiting
            
            time.sleep(2)  # Between queries
        
        logger.info(f"🎬 Scan complete. Added {added} new videos.")
        return added
    
    def quick_add(self, url: str) -> bool:
        """Quickly add a single video by URL"""
        video_info = self.get_video_info(url)
        if video_info:
            return self.add_video(video_info)
        return False

def main():
    import sys
    
    curator = RobotCurator()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == 'add' and len(sys.argv) > 2:
            url = sys.argv[2]
            if curator.quick_add(url):
                print("✅ Video added!")
            else:
                print("❌ Failed to add video")
        elif sys.argv[1] == 'scan':
            max_per = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            added = curator.run_scan(max_per)
            print(f"Added {added} videos")
        else:
            print("Usage:")
            print("  python robot_curator.py scan [max_per_query]")
            print("  python robot_curator.py add <youtube_url>")
    else:
        # Default: run scan
        curator.run_scan()

if __name__ == '__main__':
    main()
