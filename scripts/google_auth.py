"""One-time Google OAuth2 authorization flow.

Run this script to authorize Taskforce with your Google account.
It will open a browser window for consent and save the token to
~/.taskforce/google_token.json.

Usage:
    python scripts/google_auth.py

The token file will be used automatically by the calendar, gmail,
and tasks tools.
"""

from __future__ import annotations

import json
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/tasks.readonly",
]

CREDENTIALS_FILE = Path.home() / ".taskforce" / "google_credentials.json"
TOKEN_FILE = Path.home() / ".taskforce" / "google_token.json"


def main() -> None:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("ERROR: Missing dependency. Install with:")
        print("  uv sync --extra personal-assistant")
        print("  # or: pip install google-auth-oauthlib")
        return

    if not CREDENTIALS_FILE.exists():
        print(f"ERROR: Client secret not found at {CREDENTIALS_FILE}")
        print("Copy your OAuth client secret JSON file there first.")
        return

    print(f"Starting OAuth flow with scopes:")
    for scope in SCOPES:
        print(f"  - {scope.split('/')[-1]}")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_FILE),
        scopes=SCOPES,
    )

    # This opens a browser for consent
    creds = flow.run_local_server(port=0)

    # Save the token
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
    }
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
    print(f"\nToken saved to {TOKEN_FILE}")
    print("Taskforce tools (calendar, gmail, tasks) can now use this token.")


if __name__ == "__main__":
    main()
