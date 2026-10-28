import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
load_dotenv(BASE_DIR / ".env")


def env(name, default=None):
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def int_env(name, default=None):
    value = env(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def secret_key():
    key = env("SECRET_KEY")
    if key:
        return key
    INSTANCE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = INSTANCE_DIR / "flask-secret-key"
    try:
        key = path.read_text(encoding="utf-8").strip()
        if key:
            return key
    except OSError:
        pass
    key = secrets.token_hex(32)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as secret_file:
            secret_file.write(key)
        return key
    except FileExistsError:
        return path.read_text(encoding="utf-8").strip()


DOMAIN = "osuokayu.pw"
BASE_URL = env("BASE_URL", f"https://{DOMAIN}").rstrip("/")
MAX_UPLOAD_BYTES = int_env("MAX_UPLOAD_BYTES", 32 * 1024 * 1024)
