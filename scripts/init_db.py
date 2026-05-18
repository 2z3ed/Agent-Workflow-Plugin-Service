from app.database import init_db
from app.plugins.email.repository import init_email_db


if __name__ == "__main__":
    init_db()
    init_email_db()
    print("SQLite databases initialized successfully.")
