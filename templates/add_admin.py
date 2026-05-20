import sqlite3
conn=sqlite3.connect("database.db")
conn.execute("UPDATE users SET role='admin' WHERE email='your_email'")
conn.commit()
