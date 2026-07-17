"""Run the same additive, idempotent schema migration used at application boot."""

from app.models.database import create_tables


if __name__ == "__main__":
    print("Applying additive database migrations...")
    create_tables()
    print("Database schema is current.")
