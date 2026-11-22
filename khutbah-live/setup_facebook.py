#!/usr/bin/env python3
"""One-time: connect the masjid's Facebook Page.  python3 setup_facebook.py

You need a Facebook app (App ID + App Secret) and a short-lived user token from the
Graph API Explorer with the permissions listed in the README. This exchanges it for a
Page token that does not expire, and stores it in data/secrets.json.
"""

import getpass

from common import http, load_config, update_secrets


def main():
    version = load_config().get("facebook", {}).get("graphApiVersion", "v25.0")
    base = f"https://graph.facebook.com/{version}"

    app_id = input("App ID: ").strip()
    app_secret = getpass.getpass("App Secret (hidden): ").strip()
    short_token = getpass.getpass("User token from Graph API Explorer (hidden): ").strip()

    long_user = http("GET", f"{base}/oauth/access_token", params={
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_token,
    })["access_token"]

    pages = http("GET", f"{base}/me/accounts", params={
        "fields": "id,name,access_token,tasks", "access_token": long_user,
    }).get("data", [])
    if not pages:
        raise SystemExit("No Pages found. Make sure you ticked the masjid's Page when granting access.")

    for i, p in enumerate(pages, 1):
        print(f"  {i}. {p['name']}  (id {p['id']})")
    choice = 1 if len(pages) == 1 else int(input("Which Page? Enter the number: "))
    page = pages[choice - 1]
    if "CREATE_CONTENT" not in page.get("tasks", ["CREATE_CONTENT"]):
        print("Warning: your account may not be allowed to post on this Page.")

    update_secrets(facebook_page_id=page["id"], facebook_page_token=page["access_token"])

    debug = http("GET", f"{base}/debug_token", params={
        "input_token": page["access_token"], "access_token": f"{app_id}|{app_secret}",
    }).get("data", {})
    expires = debug.get("expires_at", 0)
    print(f"Facebook connected: {page['name']}")
    print("Page token never expires." if not expires else
          "Note: this Page token expires - re-run this script before it does.")
    missing = {"pages_manage_posts", "pages_read_engagement"} - set(debug.get("scopes", []))
    if missing:
        print(f"Warning: token is missing permissions: {', '.join(sorted(missing))}")


if __name__ == "__main__":
    main()
