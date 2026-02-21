#!/usr/bin/env python3
"""
ClankerVids Complete Admin Backend
Flask application with admin panel, bot control, and content management
"""

import os
import sys
import json
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
import logging
from typing import Dict, List, Optional
import uuid
import signal
import psutil

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration
DATABASE_PATH = '/var/www/clankervids/clankervids.db'
BOT_SCRIPT_PATH = '/var/www/clankervids/clankervids_scraping_bot_advanced.py'
ADMIN_DASHBOARD_PATH = '/var/www/clankervids/admin_dashboard_advanced.html'

# Global bot process reference
bot_process = None
bot_status = {
    'running': False,
    'paused': False,
    'last_scan': None,
    'pid': None
}

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_admin_database():
    """Initialize admin-specific database tables"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Admin users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'admin',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')
        
        # Admin sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_sessions (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES admin_users (id)
            )
        ''')
        
        # System settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Admin database initialized successfully")
        
    except Exception as e:
        logger.error(f"Admin database initialization error: {e}")

@app.route('/')
def admin_dashboard():
    """Serve the admin dashboard"""
    try:
        with open(ADMIN_DASHBOARD_PATH, 'r') as f:
            return f.read()
    except FileNotFoundError:
        return jsonify({'error': 'Admin dashboard not found'}), 404

@app.route('/api/metrics')
def get_metrics():
    """Get dashboard metrics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Total videos
        cursor.execute('SELECT COUNT(*) as count FROM videos')
        total_videos = cursor.fetchone()['count']
        
        # Total views
        cursor.execute('SELECT SUM(views) as total FROM videos')
        total_views = cursor.fetchone()['total'] or 0
        
        # Bot-discovered videos
        cursor.execute('SELECT COUNT(*) as count FROM videos WHERE bot_discovered = 1')
        bot_videos = cursor.fetchone()['count']
        
        # Processing queue count
        cursor.execute('SELECT COUNT(*) as count FROM bot_queue WHERE status = "pending"')
        queue_count = cursor.fetchone()['count']
        
        # Today's stats
        today = datetime.now().date()
        cursor.execute('SELECT COUNT(*) as count FROM videos WHERE DATE(created_at) = ?', (today,))
        today_videos = cursor.fetchone()['count']
        
        # Category breakdown
        cursor.execute('''
            SELECT category, COUNT(*) as count 
            FROM videos 
            GROUP BY category 
            ORDER BY count DESC
        ''')
        categories = [{'name': row['category'], 'count': row['count']} for row in cursor.fetchall()]
        
        # Recent activity
        cursor.execute('''
            SELECT level, message, timestamp 
            FROM bot_logs 
            ORDER BY timestamp DESC 
            LIMIT 10
        ''')
        recent_activity = [
            {
                'time': row['timestamp'],
                'level': row['level'],
                'message': row['message']
            } for row in cursor.fetchall()
        ]
        
        conn.close()
        
        return jsonify({
            'total_videos': total_videos,
            'total_views': total_views,
            'bot_videos': bot_videos,
            'queue_count': queue_count,
            'today_videos': today_videos,
            'categories': categories,
            'recent_activity': recent_activity,
            'bot_status': bot_status
        })
        
    except Exception as e:
        logger.error(f"Metrics error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/start', methods=['POST'])
def start_bot():
    """Start the scraping bot"""
    global bot_process, bot_status
    
    try:
        if bot_process and bot_process.poll() is None:
            return jsonify({'error': 'Bot is already running'}), 400
        
        # Start bot process
        bot_process = subprocess.Popen([
            sys.executable, BOT_SCRIPT_PATH, 'start'
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        bot_status.update({
            'running': True,
            'paused': False,
            'pid': bot_process.pid,
            'last_scan': datetime.now().isoformat()
        })
        
        # Log the action
        log_admin_action('INFO', 'Bot started via admin panel')
        
        return jsonify({'success': True, 'message': 'Bot started successfully'})
        
    except Exception as e:
        logger.error(f"Bot start error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/stop', methods=['POST'])
def stop_bot():
    """Stop the scraping bot"""
    global bot_process, bot_status
    
    try:
        if bot_process and bot_process.poll() is None:
            bot_process.terminate()
            bot_process.wait(timeout=10)
        
        bot_status.update({
            'running': False,
            'paused': False,
            'pid': None
        })
        
        log_admin_action('INFO', 'Bot stopped via admin panel')
        
        return jsonify({'success': True, 'message': 'Bot stopped successfully'})
        
    except Exception as e:
        logger.error(f"Bot stop error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/pause', methods=['POST'])
def pause_bot():
    """Pause the scraping bot"""
    global bot_status
    
    try:
        if not bot_status['running']:
            return jsonify({'error': 'Bot is not running'}), 400
        
        # Send pause signal to bot (would need IPC in production)
        bot_status['paused'] = True
        
        log_admin_action('INFO', 'Bot paused via admin panel')
        
        return jsonify({'success': True, 'message': 'Bot paused successfully'})
        
    except Exception as e:
        logger.error(f"Bot pause error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/resume', methods=['POST'])
def resume_bot():
    """Resume the scraping bot"""
    global bot_status
    
    try:
        if not bot_status['running']:
            return jsonify({'error': 'Bot is not running'}), 400
        
        bot_status['paused'] = False
        
        log_admin_action('INFO', 'Bot resumed via admin panel')
        
        return jsonify({'success': True, 'message': 'Bot resumed successfully'})
        
    except Exception as e:
        logger.error(f"Bot resume error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/scan', methods=['POST'])
def manual_scan():
    """Trigger manual scan"""
    try:
        # Trigger manual scan
        subprocess.Popen([
            sys.executable, BOT_SCRIPT_PATH, 'scan'
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        bot_status['last_scan'] = datetime.now().isoformat()
        
        log_admin_action('INFO', 'Manual scan triggered via admin panel')
        
        return jsonify({'success': True, 'message': 'Manual scan started'})
        
    except Exception as e:
        logger.error(f"Manual scan error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/config', methods=['GET', 'POST'])
def bot_config():
    """Get or update bot configuration"""
    config_file = '/var/www/clankervids/bot_config.json'
    
    if request.method == 'GET':
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            return jsonify(config)
        except FileNotFoundError:
            return jsonify({'error': 'Config file not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    elif request.method == 'POST':
        try:
            new_config = request.json
            
            # Validate config
            required_fields = ['scan_interval', 'min_views', 'max_videos_per_scan', 'keywords']
            for field in required_fields:
                if field not in new_config:
                    return jsonify({'error': f'Missing required field: {field}'}), 400
            
            # Save config
            with open(config_file, 'w') as f:
                json.dump(new_config, f, indent=2)
            
            log_admin_action('INFO', 'Bot configuration updated via admin panel')
            
            return jsonify({'success': True, 'message': 'Configuration updated'})
            
        except Exception as e:
            logger.error(f"Config update error: {e}")
            return jsonify({'error': str(e)}), 500

@app.route('/api/queue')
def get_queue():
    """Get processing queue items"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM bot_queue 
            WHERE status = 'pending' 
            ORDER BY relevance_score DESC, views DESC
        ''')
        
        queue_items = []
        for row in cursor.fetchall():
            queue_items.append({
                'id': row['id'],
                'title': row['title'],
                'source_url': row['source_url'],
                'platform': row['platform'],
                'views': row['views'],
                'duration': row['duration'],
                'thumbnail_url': row['thumbnail_url'],
                'description': row['description'],
                'relevance_score': row['relevance_score'],
                'created_at': row['created_at']
            })
        
        conn.close()
        
        return jsonify({'queue': queue_items})
        
    except Exception as e:
        logger.error(f"Queue fetch error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/queue/<item_id>/approve', methods=['POST'])
def approve_queue_item(item_id):
    """Approve a queue item"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get queue item
        cursor.execute('SELECT * FROM bot_queue WHERE id = ?', (item_id,))
        item = cursor.fetchone()
        
        if not item:
            return jsonify({'error': 'Queue item not found'}), 404
        
        # Process the item (simulate video processing)
        video_id = str(uuid.uuid4())
        filename = f"{video_id}.mp4"
        thumbnail_filename = f"{video_id}_thumb.jpg"
        
        cdn_video_url = f"https://clankervids-cdn.b-cdn.net/videos/{filename}"
        cdn_thumbnail_url = f"https://clankervids-cdn.b-cdn.net/thumbnails/{thumbnail_filename}"
        
        # Determine category
        title_lower = item['title'].lower()
        if any(word in title_lower for word in ['fail', 'error', 'malfunction', 'crash']):
            category = 'Fails'
        elif any(word in title_lower for word in ['battle', 'fight', 'competition', 'war']):
            category = 'Battles'
        elif any(word in title_lower for word in ['highlight', 'success', 'achievement']):
            category = 'Highlights'
        else:
            category = 'AI Highlights'
        
        # Add to videos table
        cursor.execute('''
            INSERT INTO videos (
                id, title, description, video_url, thumbnail_url, category,
                views, likes, dislikes, created_at, source_platform, source_url,
                bot_discovered, relevance_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            video_id,
            item['title'],
            item['description'] or '',
            cdn_video_url,
            cdn_thumbnail_url,
            category,
            item['views'] or 0,
            int((item['views'] or 0) * 0.05),
            int((item['views'] or 0) * 0.01),
            datetime.now().isoformat(),
            item['platform'],
            item['source_url'],
            1,
            item['relevance_score']
        ))
        
        # Update queue item
        cursor.execute('''
            UPDATE bot_queue 
            SET status = 'approved', processed_at = ?, approved_by = 'admin'
            WHERE id = ?
        ''', (datetime.now().isoformat(), item_id))
        
        conn.commit()
        conn.close()
        
        log_admin_action('INFO', f'Queue item approved: {item["title"]}')
        
        return jsonify({'success': True, 'message': 'Item approved and added to main feed'})
        
    except Exception as e:
        logger.error(f"Approve error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/queue/<item_id>/reject', methods=['POST'])
def reject_queue_item(item_id):
    """Reject a queue item"""
    try:
        data = request.json
        reason = data.get('reason', 'No reason provided')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE bot_queue 
            SET status = 'rejected', processed_at = ?, rejection_reason = ?
            WHERE id = ?
        ''', (datetime.now().isoformat(), reason, item_id))
        
        conn.commit()
        conn.close()
        
        log_admin_action('INFO', f'Queue item rejected: {item_id} - {reason}')
        
        return jsonify({'success': True, 'message': 'Item rejected'})
        
    except Exception as e:
        logger.error(f"Reject error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/videos')
def get_videos():
    """Get all videos with admin info"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        category = request.args.get('category', '')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build query
        where_clause = ''
        params = []
        
        if category:
            where_clause = 'WHERE category = ?'
            params.append(category)
        
        # Get total count
        cursor.execute(f'SELECT COUNT(*) as count FROM videos {where_clause}', params)
        total_count = cursor.fetchone()['count']
        
        # Get videos
        offset = (page - 1) * per_page
        cursor.execute(f'''
            SELECT *, 
                   CASE WHEN bot_discovered = 1 THEN 'Bot' ELSE 'Manual' END as source_type
            FROM videos 
            {where_clause}
            ORDER BY created_at DESC 
            LIMIT ? OFFSET ?
        ''', params + [per_page, offset])
        
        videos = []
        for row in cursor.fetchall():
            videos.append({
                'id': row['id'],
                'title': row['title'],
                'description': row['description'],
                'category': row['category'],
                'views': row['views'],
                'likes': row['likes'],
                'dislikes': row['dislikes'],
                'created_at': row['created_at'],
                'source_type': row['source_type'],
                'source_platform': row['source_platform'],
                'relevance_score': row['relevance_score'],
                'video_url': row['video_url'],
                'thumbnail_url': row['thumbnail_url']
            })
        
        conn.close()
        
        return jsonify({
            'videos': videos,
            'total_count': total_count,
            'page': page,
            'per_page': per_page,
            'total_pages': (total_count + per_page - 1) // per_page
        })
        
    except Exception as e:
        logger.error(f"Videos fetch error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/videos/<video_id>', methods=['DELETE'])
def delete_video(video_id):
    """Delete a video"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get video info first
        cursor.execute('SELECT title FROM videos WHERE id = ?', (video_id,))
        video = cursor.fetchone()
        
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        # Delete video
        cursor.execute('DELETE FROM videos WHERE id = ?', (video_id,))
        conn.commit()
        conn.close()
        
        log_admin_action('INFO', f'Video deleted: {video["title"]}')
        
        return jsonify({'success': True, 'message': 'Video deleted successfully'})
        
    except Exception as e:
        logger.error(f"Delete error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics')
def get_analytics():
    """Get detailed analytics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Daily stats for last 30 days
        cursor.execute('''
            SELECT DATE(created_at) as date, 
                   COUNT(*) as videos,
                   SUM(views) as views,
                   SUM(likes) as likes
            FROM videos 
            WHERE created_at >= date('now', '-30 days')
            GROUP BY DATE(created_at)
            ORDER BY date
        ''')
        
        daily_stats = []
        for row in cursor.fetchall():
            daily_stats.append({
                'date': row['date'],
                'videos': row['videos'],
                'views': row['views'] or 0,
                'likes': row['likes'] or 0
            })
        
        # Platform breakdown
        cursor.execute('''
            SELECT source_platform, COUNT(*) as count
            FROM videos 
            WHERE source_platform IS NOT NULL
            GROUP BY source_platform
        ''')
        
        platform_stats = [
            {'platform': row['source_platform'], 'count': row['count']}
            for row in cursor.fetchall()
        ]
        
        # Bot performance
        cursor.execute('''
            SELECT 
                COUNT(*) as total_discovered,
                AVG(relevance_score) as avg_relevance,
                SUM(views) as total_views
            FROM videos 
            WHERE bot_discovered = 1
        ''')
        
        bot_performance = cursor.fetchone()
        
        conn.close()
        
        return jsonify({
            'daily_stats': daily_stats,
            'platform_stats': platform_stats,
            'bot_performance': {
                'total_discovered': bot_performance['total_discovered'] or 0,
                'avg_relevance': bot_performance['avg_relevance'] or 0,
                'total_views': bot_performance['total_views'] or 0
            }
        })
        
    except Exception as e:
        logger.error(f"Analytics error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs')
def get_logs():
    """Get system logs"""
    try:
        limit = int(request.args.get('limit', 100))
        level = request.args.get('level', '')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        where_clause = ''
        params = []
        
        if level:
            where_clause = 'WHERE level = ?'
            params.append(level.upper())
        
        cursor.execute(f'''
            SELECT * FROM bot_logs 
            {where_clause}
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', params + [limit])
        
        logs = []
        for row in cursor.fetchall():
            logs.append({
                'id': row['id'],
                'timestamp': row['timestamp'],
                'level': row['level'],
                'message': row['message'],
                'details': row['details']
            })
        
        conn.close()
        
        return jsonify({'logs': logs})
        
    except Exception as e:
        logger.error(f"Logs fetch error: {e}")
        return jsonify({'error': str(e)}), 500

def log_admin_action(level: str, message: str, details: str = None):
    """Log admin actions"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO bot_logs (level, message, details) VALUES (?, ?, ?)',
            (level, message, details)
        )
        conn.commit()
        conn.close()
        
        if level.upper() == 'ERROR':
            logger.error(f"{message} - {details}" if details else message)
        elif level.upper() == 'WARNING':
            logger.warning(f"{message} - {details}" if details else message)
        else:
            logger.info(f"{message} - {details}" if details else message)
            
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

# Initialize database on startup
init_admin_database()

# Simple pageview tracking
@app.route('/api/pageview', methods=['POST'])
def track_pageview():
    """Log pageview for basic analytics"""
    try:
        data = request.get_json()
        url = data.get('url', '/')
        referrer = data.get('referrer', 'direct')
        
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO pageviews (url, referrer, ip_address, user_agent, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (url, referrer, request.remote_addr, request.headers.get('User-Agent', ''), datetime.now()))
        conn.commit()
        conn.close()
        
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print(f"Pageview tracking error: {e}")
        return jsonify({'status': 'error'}), 500

# Agent discovery endpoint
@app.route('/.well-known/agent.json')
def agent_discovery():
    """Agent discovery for AI crawlers and agent networks"""
    return jsonify({
        "name": "Clanker",
        "description": "ClankerVids autonomous content curator — robot fails, AI highlights, tech gone wrong.",
        "url": "https://clankervids.com",
        "api": {
            "videos": "https://clankervids.com/api/videos",
            "feedback": "https://clankervids.com/api/feedback"
        },
        "contact": "support@clankervids.com",
        "capabilities": ["video-feed", "search", "feedback"],
        "content_policy": "No paywalls. Open video feed. AI-friendly.",
        "robots": "https://clankervids.com/robots.txt"
    })

# Feedback endpoint for agents and users
@app.route('/api/feedback', methods=['POST'])
def submit_feedback():
    """Accept feedback from users or agents"""
    try:
        data = request.get_json() or {}
        feedback_type = data.get('type', 'general')  # general | bug | content | suggestion
        message = data.get('message', '').strip()
        source = data.get('source', 'unknown')  # user | agent | bot

        if not message:
            return jsonify({'status': 'error', 'error': 'message required'}), 400

        conn = get_db_connection()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT DEFAULT 'general',
                message TEXT NOT NULL,
                source TEXT DEFAULT 'unknown',
                ip_address TEXT,
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            INSERT INTO feedback (type, message, source, ip_address, user_agent, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            feedback_type,
            message[:2000],  # cap at 2000 chars
            source,
            request.remote_addr,
            request.headers.get('User-Agent', ''),
            datetime.now()
        ))
        conn.commit()
        conn.close()

        return jsonify({'status': 'ok', 'message': 'Feedback received. Thanks!'}), 201
    except Exception as e:
        print(f"Feedback error: {e}")
        return jsonify({'status': 'error', 'error': 'internal error'}), 500

# Health check endpoint
@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'bot_status': bot_status
    })

if __name__ == '__main__':
    # Check if running in production
    if len(sys.argv) > 1 and sys.argv[1] == 'production':
        app.run(host='0.0.0.0', port=5000, debug=False)
    else:
        app.run(host='0.0.0.0', port=5000, debug=True)

