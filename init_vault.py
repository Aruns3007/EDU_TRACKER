import sqlite3
import os

# 1. Locate your database
base_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(base_dir, 'instance', 'database.db')

def create_vault_table():
    try:
        # Connect to the SQLite file
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 2. The SQL Command for your Academic Vault
        sql_command = """
        CREATE TABLE IF NOT EXISTS student_docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            doc_type TEXT,
            upload_date DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """

        cursor.execute(sql_command)
        conn.commit()
        conn.close()
        print(">>> SUCCESS: Student Academic Vault table created!")
    except Exception as e:
        print(f">>> ERROR: {e}")

if __name__ == "__main__":
    # Ensure the instance folder exists
    if not os.path.exists(os.path.join(base_dir, 'instance')):
        os.makedirs(os.path.join(base_dir, 'instance'))
    
    create_vault_table()