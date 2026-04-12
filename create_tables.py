import sqlite3

# Connect to the database (will create if not exists)
conn = sqlite3.connect('database/marg_darshak.db')
cursor = conn.cursor()

# Create example tables (you can adjust as needed)
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    email TEXT UNIQUE,
    password_hash TEXT,
    is_premium BOOLEAN DEFAULT 0,
    mentor_access BOOLEAN DEFAULT 0,
    premium_expiry DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS mentor_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    utr TEXT,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS careers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    career_name TEXT,
    description TEXT,
    skills TEXT,
    roadmap TEXT
)
''')

conn.commit()
conn.close()

print("✅ Database tables created successfully!")
