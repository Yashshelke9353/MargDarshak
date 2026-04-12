import sqlite3

conn = sqlite3.connect('database/marg_darshak.db')
cursor = conn.cursor()
cursor.execute('SELECT name FROM sqlite_master WHERE type="table"')
tables = cursor.fetchall()
print('Tables:', tables)

# Check user_essentials table structure
try:
    cursor.execute('PRAGMA table_info(user_essentials)')
    columns = cursor.fetchall()
    print('user_essentials columns:', columns)
except:
    print('user_essentials table does not exist')

conn.close()