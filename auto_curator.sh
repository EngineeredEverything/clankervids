#!/bin/bash
# ClankerVids Auto Curator - runs every 6 hours
cd /var/www/clankervids

# Scan Reddit for new videos
/usr/bin/python3 reddit_curator.py scan 15 >> /var/log/clankervids_auto_curator.log 2>&1

# Regenerate sitemap
/usr/bin/python3 generate_sitemap.py >> /var/log/clankervids_auto_curator.log 2>&1
