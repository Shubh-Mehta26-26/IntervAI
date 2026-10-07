"""Create local configuration without overwriting existing credentials."""

import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / ".env"
content = path.read_text() if path.exists() else (root / ".env.example").read_text()
lines = content.splitlines()
found = False
for index, line in enumerate(lines):
    if line.startswith("AUTH_SECRET="):
        found = True
        if not line.partition("=")[2].strip():
            lines[index] = f"AUTH_SECRET={secrets.token_urlsafe(48)}"
if not found:
    lines.append(f"AUTH_SECRET={secrets.token_urlsafe(48)}")
path.write_text("\n".join(lines) + "\n")
print("Local environment ready. Existing configuration preserved; secrets are not printed.")
