import sqlite3

conn = sqlite3.connect("database.db")

cursor = conn.cursor()

cursor.execute("""

CREATE TABLE IF NOT EXISTS contact_messages(

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    name TEXT,

    email TEXT,

    subject TEXT,

    message TEXT

)

""")

conn.commit()

conn.close()

print("DONE")
