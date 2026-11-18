"""Create local Docker configuration without overwriting existing secrets."""

from pathlib import Path
import os
import secrets
import sys


def main() -> int:
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is required.", file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parents[1]
    target = root / ".env"
    if target.exists():
        if "GENERATE_WITH_SETUP" in target.read_text(encoding="utf-8"):
            print(".env still contains placeholder secrets. Rename that unused file, then run setup again.", file=sys.stderr)
            return 1
        print("Existing .env preserved. Start with: docker compose up --build")
        return 0
    template = (root / ".env.example").read_text(encoding="utf-8")
    replacements = {
        "POSTGRES_PASSWORD": secrets.token_hex(24),
        "REDIS_PASSWORD": secrets.token_hex(24),
        "JWT_SECRET": secrets.token_urlsafe(48),
        "METRICS_TOKEN": secrets.token_urlsafe(32),
    }
    for name, value in replacements.items():
        template = template.replace(f"{name}=GENERATE_WITH_SETUP", f"{name}={value}")
    # Exclusive creation also prevents concurrent setup processes replacing secrets.
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
        output.write(template)
    print("Created local configuration with fresh secrets.")
    print("Run: docker compose up --build")
    print("Dashboard: http://localhost:8080   API docs: http://localhost:8000/docs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
