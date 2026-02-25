#!/usr/bin/env python3
"""
ClankerVids Working Backend - Uses the database with actual video content
"""

import os
import re
import sqlite3
import json
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_file, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Database path with the actual videos
DATABASE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'clankervids.db')

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# VIDEO ENDPOINTS
# ============================================================

@app.route('/api/videos', methods=['GET'])
def get_videos():
    """Get all videos from the database"""
    try:
        category = request.args.get('category', 'all')
        sort_by = request.args.get('sort', 'recent')
        limit = request.args.get('limit', None)

        conn = get_db_connection()

        # Build query based on category
        where = "WHERE status = 'active'"
        params = []
        if category != 'all':
            where += " AND category = ?"
            params.append(category)

        # Add sorting
        if sort_by == 'recent':
            order = " ORDER BY created_at DESC"
        elif sort_by == 'popular':
            order = " ORDER BY views DESC"
        elif sort_by == 'clanks':
            order = " ORDER BY clanks DESC"
        elif sort_by == 'trending':
            # Trending: (reactions + views) created in last 7 days, ranked by engagement
            seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
            where += " AND created_at >= ?"
            params.append(seven_days_ago)
            order = " ORDER BY (clanks * 10 + system_errors * 5 + views) DESC"
        else:
            order = " ORDER BY created_at DESC"

        query = f"SELECT * FROM videos {where}{order}"
        if limit:
            query += f" LIMIT {int(limit)}"

        cursor = conn.execute(query, params)

        videos = []
        for row in cursor.fetchall():
            video = {
                'id': row['id'],
                'title': row['title'],
                'description': row['description'],
                'creator': row['creator'],
                'category': row['category'],
                'created_at': row['created_at'],
                'views': row['views'],
                'clanks': row['clanks'],
                'clank_count': row['clanks'],
                'epic_bots': row['epic_bots'],
                'epic_count': row['epic_bots'],
                'system_errors': row['system_errors'],
                'fail_count': row['system_errors'],
                'comments': row['comments'],
                'shares': row['shares'],
                'video_url': row['video_url'],
                'thumbnail_url': row['thumbnail_url'],
                'duration': row['duration'],
                'status': 'active',
                'hashtags': None,
                'view_count': row['views'],
                'upload_date': row['created_at'],
                'youtube_id': row['youtube_id'] if 'youtube_id' in row.keys() else None
            }
            videos.append(video)

        conn.close()

        response = jsonify(videos)
        response.headers['Cache-Control'] = 'public, max-age=60'
        return response

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'videos': []
        }), 500


@app.route('/api/react', methods=['POST'])
def react_to_video():
    """Handle video reactions"""
    try:
        data = request.get_json()
        video_id = data.get('video_id')
        reaction_type = data.get('reaction_type')

        if not video_id or not reaction_type:
            return jsonify({'success': False, 'error': 'Missing video_id or reaction_type'}), 400

        conn = get_db_connection()

        # Update reaction count
        if reaction_type == 'clank':
            conn.execute("UPDATE videos SET clanks = clanks + 1 WHERE id = ?", (video_id,))
        elif reaction_type == 'epic_bot':
            conn.execute("UPDATE videos SET epic_bots = epic_bots + 1 WHERE id = ?", (video_id,))
        elif reaction_type in ('epic_fail', 'fail'):
            conn.execute("UPDATE videos SET system_errors = system_errors + 1 WHERE id = ?", (video_id,))

        # Also increment views
        conn.execute("UPDATE videos SET views = views + 1 WHERE id = ?", (video_id,))

        conn.commit()
        conn.close()

        return jsonify({'success': True, 'reaction': reaction_type})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    """Get top videos for leaderboard"""
    try:
        conn = get_db_connection()
        cursor = conn.execute("""
            SELECT id, title, creator, clanks, views
            FROM videos
            WHERE status = 'active'
            ORDER BY clanks DESC, views DESC
            LIMIT 10
        """)

        leaderboard = []
        for row in cursor.fetchall():
            video = {
                'id': row['id'],
                'title': row['title'],
                'creator': row['creator'],
                'clanks': row['clanks'],
                'views': row['views']
            }
            leaderboard.append(video)

        conn.close()

        return jsonify(leaderboard)

    except Exception as e:
        return jsonify([]), 500


# ============================================================
# EMAIL SUBSCRIBE
# ============================================================

@app.route('/api/subscribe', methods=['POST'])
def subscribe_email():
    """Subscribe an email address"""
    try:
        data = request.get_json() or {}
        email = (data.get('email') or '').strip().lower()

        # Basic validation
        if not email or not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            return jsonify({'success': False, 'error': 'Invalid email address'}), 400

        conn = get_db_connection()

        # Ensure table exists
        conn.execute('''
            CREATE TABLE IF NOT EXISTS email_subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip_address TEXT,
                confirmed BOOLEAN DEFAULT 0,
                unsubscribed BOOLEAN DEFAULT 0
            )
        ''')

        # Check if already subscribed
        existing = conn.execute(
            "SELECT id, unsubscribed FROM email_subscribers WHERE email = ?", (email,)
        ).fetchone()

        if existing:
            if existing['unsubscribed']:
                conn.execute(
                    "UPDATE email_subscribers SET unsubscribed = 0 WHERE email = ?", (email,)
                )
                conn.commit()
                conn.close()
                return jsonify({'success': True, 'message': 'Welcome back! You are re-subscribed.'})
            conn.close()
            return jsonify({'success': True, 'message': 'You are already subscribed!'})

        conn.execute(
            "INSERT INTO email_subscribers (email, ip_address) VALUES (?, ?)",
            (email, request.remote_addr)
        )
        conn.commit()
        conn.close()

        # Send welcome email (non-blocking — best effort)
        try:
            import sys as _sys
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location(
                'email_service',
                os.path.join(os.path.dirname(os.path.dirname(__file__)), 'email_service.py')
            )
            _em = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_em)
            _em.send_welcome(email)
        except Exception as _e:
            print(f"Welcome email error (non-fatal): {_e}")

        return jsonify({'success': True, 'message': 'Subscribed! Daily robot content incoming. 🤖'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ANALYTICS
# ============================================================

@app.route('/api/pageview', methods=['POST'])
def track_pageview():
    """Log pageview for basic analytics"""
    try:
        data = request.get_json() or {}
        url = data.get('url', '/')
        referrer = data.get('referrer', 'direct') or 'direct'

        conn = get_db_connection()

        # Ensure pageviews table exists
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pageviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                referrer TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute(
            "INSERT INTO pageviews (url, referrer, ip_address, user_agent, created_at) VALUES (?, ?, ?, ?, ?)",
            (url, referrer, request.remote_addr, request.headers.get('User-Agent', ''), datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

        return jsonify({'status': 'ok'}), 200

    except Exception as e:
        return jsonify({'status': 'error'}), 500


@app.route('/api/analytics-stats', methods=['GET'])
def get_analytics_stats():
    """Return analytics summary for the dashboard"""
    try:
        conn = get_db_connection()

        # Total videos
        total_videos = conn.execute(
            "SELECT COUNT(*) as c FROM videos WHERE status='active'"
        ).fetchone()['c']

        # Total views + reactions
        agg = conn.execute(
            "SELECT SUM(views) as tv, SUM(clanks + system_errors) as tr FROM videos WHERE status='active'"
        ).fetchone()
        total_views = agg['tv'] or 0
        total_reactions = agg['tr'] or 0

        # Category breakdown
        cat_rows = conn.execute(
            "SELECT category, COUNT(*) as c FROM videos WHERE status='active' GROUP BY category ORDER BY c DESC"
        ).fetchall()
        categories = [{'category': r['category'], 'count': r['c']} for r in cat_rows]

        # Email subscriber count
        try:
            sub_count = conn.execute(
                "SELECT COUNT(*) as c FROM email_subscribers WHERE unsubscribed = 0"
            ).fetchone()['c']
        except Exception:
            sub_count = 0

        # 7-day pageview chart
        pageview_chart = []
        try:
            for i in range(6, -1, -1):
                day = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                count = conn.execute(
                    "SELECT COUNT(*) as c FROM pageviews WHERE DATE(created_at) = ?", (day,)
                ).fetchone()['c']
                pageview_chart.append({'date': day, 'count': count})
        except Exception:
            pass

        # 7-day total pageviews
        seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
        try:
            pageviews_7d = conn.execute(
                "SELECT COUNT(*) as c FROM pageviews WHERE created_at >= ?", (seven_days_ago,)
            ).fetchone()['c']
        except Exception:
            pageviews_7d = 0

        # Top referrers (7d)
        top_referrers = []
        try:
            ref_rows = conn.execute(
                """SELECT referrer, COUNT(*) as c FROM pageviews
                   WHERE created_at >= ? AND referrer IS NOT NULL AND referrer != 'direct'
                   GROUP BY referrer ORDER BY c DESC LIMIT 10""",
                (seven_days_ago,)
            ).fetchall()
            top_referrers = [{'referrer': r['referrer'], 'count': r['c']} for r in ref_rows]
        except Exception:
            pass

        # Recent pageviews
        recent_pageviews = []
        try:
            pv_rows = conn.execute(
                "SELECT url, referrer, created_at FROM pageviews ORDER BY created_at DESC LIMIT 20"
            ).fetchall()
            recent_pageviews = [{'url': r['url'], 'referrer': r['referrer'], 'created_at': r['created_at']} for r in pv_rows]
        except Exception:
            pass

        # Top 10 videos by views
        top_videos = []
        tv_rows = conn.execute(
            """SELECT title, category, views, clanks, system_errors
               FROM videos WHERE status='active'
               ORDER BY views DESC LIMIT 10"""
        ).fetchall()
        top_videos = [{
            'title': r['title'],
            'category': r['category'],
            'views': r['views'],
            'clanks': r['clanks'],
            'fails': r['system_errors']
        } for r in tv_rows]

        conn.close()

        return jsonify({
            'total_videos': total_videos,
            'total_views': total_views,
            'total_reactions': total_reactions,
            'subscriber_count': sub_count,
            'pageviews_7d': pageviews_7d,
            'categories': categories,
            'pageview_chart': pageview_chart,
            'top_referrers': top_referrers,
            'recent_pageviews': recent_pageviews,
            'top_videos': top_videos
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
# DAILY DIGEST
# ============================================================

@app.route('/api/digest', methods=['GET'])
def get_digest():
    """Get the latest daily robot digest metadata and audio URL."""
    import json as _json
    meta_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'public', 'daily_digest.json')
    audio_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'public', 'daily_digest.mp3')
    if not os.path.isfile(meta_path):
        return jsonify({'error': 'No digest available yet'}), 404
    with open(meta_path, 'r') as f:
        meta = _json.load(f)
    meta['audio_available'] = os.path.isfile(audio_path)
    resp = jsonify(meta)
    resp.headers['Cache-Control'] = 'public, max-age=300'
    return resp


# ============================================================
# HEALTH + STATIC
# ============================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        cursor = conn.execute("SELECT COUNT(*) as count FROM videos")
        video_count = cursor.fetchone()['count']
        conn.close()

        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'video_count': video_count
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@app.route('/')
def index():
    """Serve the frontend HTML"""
    frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'index.html')
    with open(frontend_path, 'r', encoding='utf-8') as f:
        content = f.read()
    response = Response(content, mimetype='text/html')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/favicon.ico')
def favicon():
    """Explicit favicon.ico route — bypasses any caching issues."""
    base = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(base, 'favicon.ico')
    resp = send_file(path, mimetype='image/vnd.microsoft.icon')
    resp.headers['Cache-Control'] = 'public, max-age=86400'
    return resp


@app.route('/<path:filename>')
def serve_static(filename):
    """Serve static files from the site root"""
    base = os.path.dirname(os.path.dirname(__file__))
    filepath = os.path.join(base, filename)
    if os.path.isfile(filepath):
        # Cache-Control for static assets
        ext = os.path.splitext(filename)[1].lower()
        resp = send_file(filepath)
        if ext in ('.html',):
            resp.headers['Cache-Control'] = 'public, max-age=300'
        elif ext in ('.png', '.jpg', '.jpeg', '.gif', '.ico', '.webp', '.svg'):
            resp.headers['Cache-Control'] = 'public, max-age=86400'
        elif ext in ('.js', '.css', '.woff', '.woff2'):
            resp.headers['Cache-Control'] = 'public, max-age=604800'
        elif ext in ('.json',):
            resp.headers['Cache-Control'] = 'public, max-age=3600'
        return resp
    return jsonify({'error': 'Not found'}), 404


@app.route('/sitemap.xml')
def sitemap():
    """Generate dynamic sitemap for SEO"""
    conn = get_db_connection()
    cursor = conn.execute("SELECT DISTINCT category FROM videos WHERE status = 'active'")
    categories = [row['category'] for row in cursor.fetchall()]
    cursor = conn.execute("SELECT MAX(created_at) as last_update FROM videos")
    last_update = cursor.fetchone()['last_update'] or datetime.now().strftime('%Y-%m-%d')
    conn.close()

    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    xml.append(f'''  <url>
    <loc>https://clankervids.com/</loc>
    <lastmod>{last_update[:10]}</lastmod>
    <changefreq>hourly</changefreq>
    <priority>1.0</priority>
  </url>''')

    for page in ['robot-fails', 'battle-bots']:
        xml.append(f'''  <url>
    <loc>https://clankervids.com/{page}.html</loc>
    <lastmod>{datetime.now().strftime('%Y-%m-%d')}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.9</priority>
  </url>''')

    for cat in categories:
        xml.append(f'''  <url>
    <loc>https://clankervids.com/?category={cat}</loc>
    <lastmod>{last_update[:10]}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>''')

    xml.append('</urlset>')
    return Response('\n'.join(xml), mimetype='application/xml')


@app.route('/robots.txt')
def robots():
    """Serve robots.txt for SEO"""
    txt = """User-agent: *
Allow: /
Disallow: /admin
Disallow: /api/

User-agent: GPTBot
Allow: /

User-agent: ChatGPT-User
Allow: /

User-agent: anthropic-ai
Allow: /

User-agent: Claude-Web
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: PerplexityBot
Allow: /

Sitemap: https://clankervids.com/sitemap.xml
"""
    return Response(txt, mimetype='text/plain')


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


@app.route('/api/feedback', methods=['POST'])
def submit_feedback():
    """Accept feedback from users or agents"""
    try:
        data = request.get_json() or {}
        feedback_type = data.get('type', 'general')
        message = data.get('message', '').strip()
        source = data.get('source', 'unknown')

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
            message[:2000],
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


if __name__ == '__main__':
    print("ClankerVids Backend Starting...")
    print(f"Database: {DATABASE_PATH}")
    try:
        conn = get_db_connection()
        cursor = conn.execute("SELECT COUNT(*) as count FROM videos")
        video_count = cursor.fetchone()['count']
        conn.close()
        print(f"Found {video_count} videos in database")
    except Exception as e:
        print(f"Database error: {e}")

    print("Starting server on http://localhost:8080")
    app.run(host='0.0.0.0', port=8080, debug=False)
