"""Environment config. Owner: Person A. Names are part of the contract; B reads, never writes."""
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./dev.db")
HISTORY_XLSX_PATH = os.environ.get("HISTORY_XLSX_PATH", "./data/email_history.xlsx")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
TIMEZONE = "Asia/Kolkata"

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "")
