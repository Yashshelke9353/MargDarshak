import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "marg_darshak.db")

print(f"DB_PATH: {DB_PATH}")
print(f"Exists: {os.path.exists(DB_PATH)}")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Simulate quiz data with all 0s
data = {'technical': 0, 'creative': 0, 'social': 0, 'analytical': 0, 'entrepreneurial': 0}

interests = {
    'technical': data.get('technical', 0),
    'creative': data.get('creative', 0),
    'social': data.get('social', 0),
    'analytical': data.get('analytical', 0),
    'entrepreneurial': data.get('entrepreneurial', 0)
}

print(f"Interests: {interests}")

sorted_interests = sorted(interests.items(), key=lambda x: x[1], reverse=True)
top_two = sorted_interests[:2]

print(f"Top two: {top_two}")

careers = []

category_mapping = {
    'technical': 'Technology',
    'creative': 'Creative',
    'social': 'Business',
    'analytical': 'Technology',
    'entrepreneurial': 'Business'
}

for interest, score in top_two:
    category = category_mapping.get(interest, 'Technology')
    print(f"Querying category: {category}")
    results = conn.execute('SELECT * FROM careers WHERE category = ? LIMIT 3', (category,)).fetchall()
    print(f"Found {len(results)} careers")
    for row in results:
        careers.append(dict(row))

conn.close()

print(f"Total careers: {len(careers)}")
print(f"First career: {careers[0] if careers else 'None'}")