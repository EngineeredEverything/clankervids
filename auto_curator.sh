#!/bin/bash
# ClankerVids Auto Curator - runs every 6 hours
cd /var/www/clankervids
/usr/bin/python3 reddit_curator.py scan 15 >> /var/log/clankervids_auto_curator.log 2>&1
