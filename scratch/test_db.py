import sqlite3
from pathlib import Path

db_path = Path("backend/database/signals.sqlite3")
print("Connecting to:", db_path.absolute())
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

print("\n--- USERS ---")
for r in conn.execute("SELECT * FROM users").fetchall():
    print(dict(r))

print("\n--- WATCHLIST ---")
for r in conn.execute("SELECT * FROM watchlist").fetchall():
    print(dict(r))

print("\n--- SIGNAL HISTORY ---")
for r in conn.execute("SELECT * FROM signal_history").fetchall():
    print(dict(r))

conn.close()
