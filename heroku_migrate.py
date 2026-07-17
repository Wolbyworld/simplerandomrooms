from sqlalchemy import create_engine, Column, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import text
import os

# Get database URL from environment
DATABASE_URL = os.environ.get("DATABASE_URL")
print(f"Using database URL: {DATABASE_URL}")

# Modify URL if it's using postgres:// instead of postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    print(f"Modified URL: {DATABASE_URL}")

# Create engine
engine = create_engine(DATABASE_URL)

def run_migration():
    print("Starting Heroku PostgreSQL migration...")
    
    # Connect to the database
    with engine.connect() as connection:
        try:
            # Check if column exists
            print("Checking if is_list_draw column exists...")
            result = connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='rooms' AND column_name='is_list_draw'"))
            column_exists = result.fetchone() is not None
            
            if not column_exists:
                print("Adding is_list_draw column to rooms table...")
                # Add the new column with default value of False
                connection.execute(text("ALTER TABLE rooms ADD COLUMN is_list_draw BOOLEAN DEFAULT FALSE"))
                print("Column added successfully.")
                
                # Commit the transaction
                connection.commit()
            else:
                print("Column is_list_draw already exists.")
            
            print("Migration completed successfully.")
        
        except Exception as e:
            print(f"Error during migration: {e}")
            # The connection will roll back automatically
    
    print("Migration script finished.")

if __name__ == "__main__":
    run_migration() 