#!/usr/bin/env python3
"""Add pageviews table for basic analytics"""

import sqlite3

DB_PATH = '/var/www/clankervids/clankervids.db'

def add_pageviews_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Create pageviews table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pageviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            referrer TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create index for faster queries
    cur.execute('''
        CREATE INDEX IF NOT EXISTS idx_pageviews_created_at 
        ON pageviews(created_at DESC)
    ''')
    
    cur.execute('''
        CREATE INDEX IF NOT EXISTS idx_pageviews_url 
        ON pageviews(url)
    ''')
    
    conn.commit()
    conn.close()
    print('✅ Pageviews table created')

if __name__ == '__main__':
    add_pageviews_table()
