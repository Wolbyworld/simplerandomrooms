"""Backward-compatible migration entry point for legacy deployment scripts."""

from app.models.database import create_tables


def run_migration() -> None:
    create_tables()


if __name__ == "__main__":
    run_migration()
