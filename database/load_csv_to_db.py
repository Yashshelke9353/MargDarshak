import pandas as pd
import sqlite3
import os

# Database path
db_path = 'database/marg_darshak.db'

# Ensure database directory exists
os.makedirs('database', exist_ok=True)

# Connect to database
conn = sqlite3.connect(db_path)

# Load careers data
careers_df = pd.read_csv('data/careers.csv')
careers_df['id'] = range(1, len(careers_df) + 1)
careers_df.to_sql('careers', conn, if_exists='replace', index=False)
print(f"✅ Loaded {len(careers_df)} careers")

# Load gyan kosh data
import csv
rows = []
with open('data/shlokas.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        rows.append([row['source'], row['chapter'], row['verse_number'], row['sanskrit_text'], row['hindi_meaning'], row['english_meaning'], row['practical_application'], row['tags'], row['audio_url']])
gyan_df = pd.DataFrame(rows, columns=['source', 'chapter', 'verse_number', 'sanskrit_text', 'hindi_meaning', 'english_meaning', 'practical_application', 'tags', 'audio_url'])
gyan_df.to_sql('gyan_kosh', conn, if_exists='replace', index=False)
print(f"✅ Loaded {len(gyan_df)} gyan kosh entries")

# Load learning resources data
resources_df = pd.read_csv('data/resources.csv')
resources_df.to_sql('learning_resources', conn, if_exists='replace', index=False)
print(f"✅ Loaded {len(resources_df)} learning resources")

# Close connection
conn.close()

print("🎉 All data loaded successfully!")