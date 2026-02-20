#!/usr/bin/env python3
"""
ClankerVids Email Service
Sends transactional and digest emails via Zoho SMTP.

To activate: set ZOHO_EMAIL_PASSWORD in /root/.openclaw/openclaw.json env section,
or pass directly. Until password is set, all sends are no-ops (logged only).
"""

import os
import json
import smtplib
import sqlite3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Zoho SMTP config
SMTP_HOST = 'smtp.zoho.com'
SMTP_PORT = 465
SMTP_USER = 'support@clankervids.com'
FROM_NAME  = 'ClankerVids 🤖'

DATABASE_PATH = '/var/www/clankervids/clankervids.db'


def _get_password():
    """Load Zoho password from openclaw.json or env."""
    pw = os.environ.get('ZOHO_EMAIL_PASSWORD', '')
    if pw:
        return pw
    try:
        with open('/root/.openclaw/openclaw.json') as f:
            cfg = json.load(f)
        return cfg.get('env', {}).get('ZOHO_EMAIL_PASSWORD', '')
    except Exception:
        return ''


def _send(to_address: str, subject: str, html_body: str, text_body: str = '') -> bool:
    """Send a single email via Zoho SMTP. Returns True on success."""
    password = _get_password()
    if not password:
        logger.warning(f"[EMAIL NO-OP] No ZOHO_EMAIL_PASSWORD set. Would send '{subject}' to {to_address}")
        return False

    msg = MIMEMultipart('alternative')
    msg['From']    = f'{FROM_NAME} <{SMTP_USER}>'
    msg['To']      = to_address
    msg['Subject'] = subject
    msg['Date']    = formatdate(localtime=False)
    msg['Message-ID'] = make_msgid(domain='clankervids.com')

    if text_body:
        msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.login(SMTP_USER, password)
            server.sendmail(SMTP_USER, [to_address], msg.as_string())
        logger.info(f"[EMAIL OK] '{subject}' → {to_address}")
        return True
    except Exception as e:
        logger.error(f"[EMAIL FAIL] '{subject}' → {to_address}: {e}")
        return False


# ============================================================
# WELCOME EMAIL
# ============================================================

WELCOME_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Welcome to ClankerVids</title>
  <style>
    body {{ margin:0; padding:0; background:#0a0a0f; font-family: 'Helvetica Neue', Arial, sans-serif; color:#fff; }}
    .wrap {{ max-width:560px; margin:40px auto; background:#111; border-radius:12px; overflow:hidden; border:1px solid #1e1e2e; }}
    .hero {{ background:linear-gradient(135deg,#0a0a1a 0%,#1a1a2e 100%); padding:40px 32px 32px; text-align:center; }}
    .logo {{ font-size:48px; margin-bottom:8px; }}
    .title {{ font-size:26px; font-weight:700; color:#00ff88; margin:0; letter-spacing:-0.5px; }}
    .tagline {{ font-size:14px; color:rgba(255,255,255,0.5); margin-top:6px; }}
    .body {{ padding:32px; }}
    .body p {{ font-size:15px; line-height:1.6; color:rgba(255,255,255,0.85); margin:0 0 16px; }}
    .cta {{ display:block; text-align:center; margin:28px 0; }}
    .cta a {{ background:#00ff88; color:#000; font-weight:700; font-size:15px; padding:14px 32px; border-radius:8px; text-decoration:none; letter-spacing:0.3px; }}
    .divider {{ border:none; border-top:1px solid #1e1e2e; margin:24px 0; }}
    .footer {{ padding:0 32px 28px; text-align:center; font-size:12px; color:rgba(255,255,255,0.3); }}
    .footer a {{ color:rgba(255,255,255,0.4); text-decoration:none; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div class="logo">🤖</div>
      <h1 class="title">ClankerVids</h1>
      <p class="tagline">The internet's best robot content, delivered.</p>
    </div>
    <div class="body">
      <p>You're in. Welcome to the only newsletter where robots fail so you don't have to.</p>
      <p>Here's what to expect:</p>
      <ul style="color:rgba(255,255,255,0.85);font-size:15px;line-height:1.8;padding-left:20px;margin:0 0 16px;">
        <li>🤖 Daily robot highlights, fails &amp; battles</li>
        <li>💥 The viral clips before they go mainstream</li>
        <li>🎙️ AI-narrated daily digest (new!)</li>
      </ul>
      <p>For now, head over and check out today's feed — updated every 6 hours.</p>
      <div class="cta"><a href="https://clankervids.com">Watch the Robots →</a></div>
    </div>
    <hr class="divider">
    <div class="footer">
      <p>You're getting this because you signed up at clankervids.com</p>
      <p><a href="https://clankervids.com">Visit Site</a> · <a href="mailto:support@clankervids.com">Contact</a></p>
    </div>
  </div>
</body>
</html>"""

WELCOME_TEXT = """Welcome to ClankerVids!

You're in. The internet's best robot fails, highlights, and battles — delivered to you.

What to expect:
- Daily robot highlights, fails & battles
- Viral clips before they go mainstream
- AI-narrated daily digest

Check today's feed: https://clankervids.com

Questions? Reply to this email or reach us at support@clankervids.com
"""

def send_welcome(to_email: str) -> bool:
    """Send a welcome email to a new subscriber."""
    return _send(
        to_address=to_email,
        subject="🤖 Welcome to ClankerVids — you're in",
        html_body=WELCOME_HTML,
        text_body=WELCOME_TEXT,
    )


# ============================================================
# WEEKLY DIGEST EMAIL
# ============================================================

def _get_top_videos(limit=5):
    """Get top videos from the last 7 days (or all time if insufficient)."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()

    cursor = conn.execute("""
        SELECT id, title, category, views, youtube_id, thumbnail_url
        FROM videos WHERE status='active' AND created_at >= ?
        ORDER BY views DESC LIMIT ?
    """, (seven_days_ago, limit))
    rows = cursor.fetchall()

    if len(rows) < 3:
        cursor = conn.execute("""
            SELECT id, title, category, views, youtube_id, thumbnail_url
            FROM videos WHERE status='active'
            ORDER BY views DESC LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()

    conn.close()
    return [dict(r) for r in rows]


def _get_active_subscribers():
    """Get all active, confirmed (or unconfirmed but subscribed) emails."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT email FROM email_subscribers
        WHERE unsubscribed = 0
        ORDER BY created_at ASC
    """)
    rows = [r['email'] for r in cursor.fetchall()]
    conn.close()
    return rows


def _video_card_html(video, rank):
    """Generate HTML for a single video card in the digest."""
    title = video['title'][:70] + ('...' if len(video['title']) > 70 else '')
    cat_emoji = {'fails': '💥', 'highlights': '✨', 'battles': '⚔️'}.get(video['category'], '🤖')
    yt_id = video.get('youtube_id', '')
    thumb = f"https://img.youtube.com/vi/{yt_id}/mqdefault.jpg" if yt_id else ''
    video_url = f"https://clankervids.com"

    img_html = f'<img src="{thumb}" width="100%" style="border-radius:6px;display:block;margin-bottom:10px;" alt="{title}">' if thumb else ''
    views = video.get('views', 0)
    views_str = f"{views/1_000_000:.1f}M views" if views >= 1_000_000 else f"{views:,} views" if views else ''

    return f"""
    <tr>
      <td style="padding:0 0 20px;">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td width="28" style="font-size:22px;vertical-align:top;padding-right:10px;padding-top:2px;">
              {cat_emoji}
            </td>
            <td>
              {img_html}
              <p style="margin:0 0 4px;font-size:15px;font-weight:600;color:#fff;line-height:1.4;">
                <a href="{video_url}" style="color:#00ff88;text-decoration:none;">{title}</a>
              </p>
              {f'<p style="margin:0;font-size:12px;color:rgba(255,255,255,0.4);">{views_str}</p>' if views_str else ''}
            </td>
          </tr>
        </table>
      </td>
    </tr>"""


def build_weekly_digest_html(videos):
    """Build the full weekly digest HTML email."""
    week_of = datetime.now().strftime('%B %d, %Y')
    video_cards = ''.join(_video_card_html(v, i+1) for i, v in enumerate(videos))

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ClankerVids Weekly Digest</title>
  <style>
    body {{ margin:0; padding:0; background:#0a0a0f; font-family:'Helvetica Neue',Arial,sans-serif; color:#fff; }}
    .wrap {{ max-width:560px; margin:40px auto; background:#111; border-radius:12px; overflow:hidden; border:1px solid #1e1e2e; }}
    .hero {{ background:linear-gradient(135deg,#0a0a1a 0%,#1a1a2e 100%); padding:32px; text-align:center; }}
    .hero h1 {{ font-size:22px; font-weight:700; color:#00ff88; margin:0; }}
    .hero p {{ font-size:13px; color:rgba(255,255,255,0.4); margin:6px 0 0; }}
    .body {{ padding:28px 32px; }}
    .section-label {{ font-size:11px; text-transform:uppercase; letter-spacing:1px; color:rgba(255,255,255,0.35); margin:0 0 16px; }}
    .cta {{ display:block; text-align:center; margin:24px 0 0; }}
    .cta a {{ background:#00ff88; color:#000; font-weight:700; font-size:14px; padding:12px 28px; border-radius:8px; text-decoration:none; }}
    .footer {{ padding:16px 32px 28px; text-align:center; font-size:11px; color:rgba(255,255,255,0.25); }}
    .footer a {{ color:rgba(255,255,255,0.3); text-decoration:none; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div style="font-size:36px;margin-bottom:8px;">🤖</div>
      <h1>Weekly Robot Roundup</h1>
      <p>Week of {week_of}</p>
    </div>
    <div class="body">
      <p class="section-label">Top videos this week</p>
      <table width="100%" cellpadding="0" cellspacing="0">
        {video_cards}
      </table>
      <div class="cta"><a href="https://clankervids.com">See All Videos →</a></div>
    </div>
    <div class="footer">
      <p>You're getting this because you subscribed at clankervids.com</p>
      <p><a href="https://clankervids.com">Visit</a> · <a href="mailto:support@clankervids.com">Unsubscribe</a></p>
    </div>
  </div>
</body>
</html>"""


def send_weekly_digest():
    """Send the weekly digest to all subscribers. Returns (sent, failed) counts."""
    subscribers = _get_active_subscribers()
    if not subscribers:
        logger.info("No subscribers — skipping digest send")
        return 0, 0

    videos = _get_top_videos(5)
    if not videos:
        logger.info("No videos found — skipping digest send")
        return 0, 0

    html = build_weekly_digest_html(videos)
    week_of = datetime.now().strftime('%B %d')
    subject = f"🤖 ClankerVids Weekly: Top Robots of the Week ({week_of})"

    sent, failed = 0, 0
    for email in subscribers:
        ok = _send(email, subject, html)
        if ok:
            sent += 1
        else:
            failed += 1

    logger.info(f"Weekly digest sent: {sent} ok, {failed} failed, {len(subscribers)} total")
    return sent, failed


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO)

    cmd = sys.argv[1] if len(sys.argv) > 1 else 'test'

    if cmd == 'welcome' and len(sys.argv) > 2:
        ok = send_welcome(sys.argv[2])
        print("Sent!" if ok else "Failed (check logs / password set?)")
    elif cmd == 'weekly':
        sent, failed = send_weekly_digest()
        print(f"Weekly digest: {sent} sent, {failed} failed")
    elif cmd == 'test':
        pw = _get_password()
        print(f"Password loaded: {'YES (' + pw[:6] + '...)' if pw else 'NO — set ZOHO_EMAIL_PASSWORD in openclaw.json'}")
        subs = _get_active_subscribers()
        print(f"Subscribers in DB: {len(subs)}")
        vids = _get_top_videos(3)
        print(f"Top videos: {[v['title'][:40] for v in vids]}")
    else:
        print("Usage: email_service.py [test|welcome <email>|weekly]")
