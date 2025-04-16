import sqlite3

print("Starting database migration...")

# Connect to the database
print("Connecting to database...")
conn = sqlite3.connect('random_draw.db')
cursor = conn.cursor()

try:
    # Check if column exists
    print("Checking if is_list_draw column exists...")
    cursor.execute("PRAGMA table_info(rooms)")
    columns = cursor.fetchall()
    print(f"Current columns: {columns}")
    column_names = [column[1] for column in columns]
    print(f"Column names: {column_names}")
    
    if 'is_list_draw' not in column_names:
        print("Adding is_list_draw column to rooms table...")
        # Add the new column with default value of 0 (False)
        cursor.execute("ALTER TABLE rooms ADD COLUMN is_list_draw BOOLEAN DEFAULT 0")
        print("Column added successfully.")
    else:
        print("Column is_list_draw already exists.")
    
    # Commit the changes
    conn.commit()
    print("Migration completed successfully.")
    
except Exception as e:
    print(f"Error during migration: {e}")
    conn.rollback()
finally:
    # Close the connection
    print("Closing database connection.")
    conn.close()
    
print("Migration script finished.") 