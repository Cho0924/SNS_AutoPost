import argparse
import json
import os
import sys

import requests
from dotenv import load_dotenv


def require_env(name):
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def optional_env(name, default_value):
    value = os.getenv(name)
    return value if value else default_value


def ensure_success(platform, response):
    if response.status_code >= 400:
        raise SystemExit(f"{platform} API error {response.status_code}: {response.text}")


def post_to_x(message, media_ids):
    token = require_env("X_USER_ACCESS_TOKEN")
    base_url = optional_env("X_API_BASE_URL", "https://api.twitter.com").rstrip("/")
    url = f"{base_url}/2/tweets"
    payload = {"text": message}
    if media_ids:
        payload["media"] = {"media_ids": media_ids}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    ensure_success("X", response)
    return response


def post_to_facebook(message, link, page_id_override):
    token = require_env("FB_PAGE_ACCESS_TOKEN")
    page_id = page_id_override or require_env("FB_PAGE_ID")
    version = optional_env("FB_GRAPH_VERSION", "v25.0")
    base_url = f"https://graph.facebook.com/{version}".rstrip("/")
    # Use /me/feed for personal account, /{page_id}/feed for page
    target = page_id
    url = f"{base_url}/{target}/feed"
    data = {"message": message, 
            "link": "https://open.spotify.com/episode/29RsUUthV7Rgs6hOWfrOBL", # テスト用URL
            "access_token": token}
    if link:
        data["link"] = link
    response = requests.post(url, data=data, timeout=30)
    ensure_success("Facebook", response)
    return response


def post_to_linkedin(message, author_urn_override):
    token = require_env("LINKEDIN_ACCESS_TOKEN")
    author_urn = author_urn_override or require_env("LINKEDIN_AUTHOR_URN")
    version = optional_env("LINKEDIN_VERSION", "202405")
    base_url = optional_env("LINKEDIN_API_BASE_URL", "https://api.linkedin.com").rstrip("/")
    api_path = optional_env("LINKEDIN_API_PATH", "/rest/posts")
    url = f"{base_url}/{api_path.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": version,
    }
    payload = {
        "author": author_urn,
        "commentary": message,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    ensure_success("LinkedIn", response)
    return response


def parse_media_ids(media_ids_text):
    if not media_ids_text:
        return []
    return [value.strip() for value in media_ids_text.split(",") if value.strip()]


def print_response(platform, response):
    result = {
        "platform": platform,
        "status": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "body": response.text,
    }
    print(json.dumps(result, indent=2))


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Post a test message to SNS platforms.")
    parser.add_argument(
        "--platform",
        choices=["x", "facebook", "linkedin", "all"],
        default="all",
        help="Target platform to post.",
    )
    parser.add_argument("--message", help="Message text to post.")
    parser.add_argument("--link", help="Link URL for Facebook feed posts.")
    parser.add_argument("--x-media-ids", help="Comma-separated X media IDs.")
    parser.add_argument("--facebook-page-id", help="Override FB page ID.")
    parser.add_argument("--linkedin-author-urn", help="Override LinkedIn author URN.")
    args = parser.parse_args()

    message = args.message or os.getenv("TEST_MESSAGE")
    if not message:
        raise SystemExit("Provide --message or set TEST_MESSAGE.")

    if args.platform in ("x", "all"):
        response = post_to_x(message, parse_media_ids(args.x_media_ids))
        print_response("x", response)

    if args.platform in ("facebook", "all"):
        response = post_to_facebook(message, args.link, args.facebook_page_id)
        print_response("facebook", response)

    if args.platform in ("linkedin", "all"):
        response = post_to_linkedin(message, args.linkedin_author_urn)
        print_response("linkedin", response)


if __name__ == "__main__":
    sys.exit(main())
