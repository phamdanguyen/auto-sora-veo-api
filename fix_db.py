import sqlite3
import os

DB_FILE = "sql_app.db"

def migrate():
    if not os.path.exists(DB_FILE):
        print("No database found, nothing to migrate.")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        # Check if columns exist
        cursor.execute("PRAGMA table_info(accounts)")
        columns = [info[1] for info in cursor.fetchall()]

        if "credits_remaining" not in columns:
            print("Adding 'credits_remaining' column...")
            cursor.execute("ALTER TABLE accounts ADD COLUMN credits_remaining INTEGER DEFAULT 0")
        
        if "credits_last_checked" not in columns:
            print("Adding 'credits_last_checked' column...")
            cursor.execute("ALTER TABLE accounts ADD COLUMN credits_last_checked TIMESTAMP")

        conn.commit()
        print("Migration completed successfully.")

    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
