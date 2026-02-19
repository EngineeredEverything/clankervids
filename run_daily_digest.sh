#!/bin/bash
# ClankerVids Daily Digest Generator
# Runs after the 6 AM auto-curator to capture fresh content

cd /var/www/clankervids

# Load ElevenLabs API key
ELEVENLABS_API_KEY=$(python3 -c "import json; d=json.load(open('/root/.openclaw/openclaw.json')); print(d['env']['ELEVENLABS_API_KEY'])" 2>/dev/null)
export ELEVENLABS_API_KEY

if [ -z "$ELEVENLABS_API_KEY" ]; then
    echo "$(date): ERROR - ELEVENLABS_API_KEY not found" >> /var/log/clankervids_digest.log
    exit 1
fi

echo "$(date): Starting daily digest generation..." >> /var/log/clankervids_digest.log
/usr/bin/python3 /var/www/clankervids/daily_digest.py >> /var/log/clankervids_digest.log 2>&1
echo "$(date): Digest generation complete (exit $?)" >> /var/log/clankervids_digest.log
