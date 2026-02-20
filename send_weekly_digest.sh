#!/bin/bash
# ClankerVids Weekly Email Digest
# Runs every Monday at 09:00 UTC

cd /var/www/clankervids

# Load Zoho email password from openclaw config
ZOHO_EMAIL_PASSWORD=$(python3 -c "import json; d=json.load(open('/root/.openclaw/openclaw.json')); print(d.get('env', {}).get('ZOHO_EMAIL_PASSWORD', ''))" 2>/dev/null)
export ZOHO_EMAIL_PASSWORD

echo "$(date): Starting weekly digest send..." >> /var/log/clankervids_email.log
/usr/bin/python3 /var/www/clankervids/email_service.py weekly >> /var/log/clankervids_email.log 2>&1
echo "$(date): Weekly digest complete (exit $?)" >> /var/log/clankervids_email.log
