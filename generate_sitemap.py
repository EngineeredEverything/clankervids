#!/usr/bin/env python3
"""
Generate sitemap.xml for ClankerVids
Run after auto-curator or manually to update sitemap
"""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = '/var/www/clankervids/clankervids.db'
SITEMAP_PATH = '/var/www/clankervids/sitemap.xml'
BASE_URL = 'https://clankervids.com'

def generate_sitemap():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Get all videos
    cur.execute('SELECT id, created_at FROM videos ORDER BY created_at DESC')
    videos = cur.fetchall()
    conn.close()
    
    # Start sitemap
    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    # Homepage - highest priority
    xml.append('  <url>')
    xml.append(f'    <loc>{BASE_URL}/</loc>')
    xml.append(f'    <lastmod>{datetime.now().strftime("%Y-%m-%d")}</lastmod>')
    xml.append('    <changefreq>hourly</changefreq>')
    xml.append('    <priority>1.0</priority>')
    xml.append('  </url>')
    
    # Category pages
    for category in ['fails', 'highlights', 'battles']:
        xml.append('  <url>')
        xml.append(f'    <loc>{BASE_URL}/?category={category}</loc>')
        xml.append(f'    <lastmod>{datetime.now().strftime("%Y-%m-%d")}</lastmod>')
        xml.append('    <changefreq>hourly</changefreq>')
        xml.append('    <priority>0.8</priority>')
        xml.append('  </url>')
    
    # Individual videos
    for video_id, created_at in videos:
        # Parse created_at (format: YYYY-MM-DD HH:MM:SS)
        try:
            date = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d')
        except:
            date = datetime.now().strftime('%Y-%m-%d')
        
        xml.append('  <url>')
        xml.append(f'    <loc>{BASE_URL}/?v={video_id}</loc>')
        xml.append(f'    <lastmod>{date}</lastmod>')
        xml.append('    <changefreq>weekly</changefreq>')
        xml.append('    <priority>0.6</priority>')
        xml.append('  </url>')
    
    xml.append('</urlset>')
    
    # Write sitemap
    Path(SITEMAP_PATH).write_text('\n'.join(xml))
    print(f'✅ Sitemap generated: {len(videos)} videos + {3} category pages + homepage')

if __name__ == '__main__':
    generate_sitemap()
