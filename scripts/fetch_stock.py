#!/usr/bin/env python3
"""Fetch free stock video/photo/gif candidates by keyword into the media library's stock cache.

Usage:
    python3 fetch_stock.py --provider pexels --query "chef cooking kitchen" --type video \
        --out-dir <media_library_path>/_stock_cache --limit 3

Requires an API key for the chosen provider, read from an environment variable
(never pass keys on the command line). If the key is missing, prints where to
get a free one and exits — it does not guess or fall back silently.

Downloaded files still need tagging like anything else in the library — feed
<out-dir>/<provider>/ through `index_media.py scan` / `write-tags` next. See
references/media_tagging_schema.md for provider licensing notes (Giphy in
particular has commercial-use restrictions worth flagging to the user).
"""
import argparse
import json
import os
import re
import sys

PROVIDERS = {
    "pexels": {
        "env": "PEXELS_API_KEY",
        "signup_url": "https://www.pexels.com/api/",
        "license_note": "Free for commercial use, no attribution required.",
    },
    "pixabay": {
        "env": "PIXABAY_API_KEY",
        "signup_url": "https://pixabay.com/api/docs/",
        "license_note": "Free for commercial use, no attribution required.",
    },
    "giphy": {
        "env": "GIPHY_API_KEY",
        "signup_url": "https://developers.giphy.com/",
        "license_note": (
            "Giphy's API terms restrict some commercial/monetized uses — check before using "
            "in anything monetized; prefer the user's own library for meme/reaction content "
            "when in doubt."
        ),
    },
}


def slugify(text, max_len=40):
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug[:max_len] or "clip"


def require_key(provider):
    info = PROVIDERS[provider]
    key = os.environ.get(info["env"])
    if not key:
        print(
            f"{info['env']} is not set — this skill will not guess or fall back silently.\n"
            f"Get a free key at {info['signup_url']} and set it, e.g.:\n"
            f"    export {info['env']}=your_key_here",
            file=sys.stderr,
        )
        sys.exit(1)
    return key


def search_pexels(query, media_type, limit, key):
    import requests

    if media_type == "video":
        url = "https://api.pexels.com/videos/search"
    else:
        url = "https://api.pexels.com/v1/search"
    resp = requests.get(
        url, headers={"Authorization": key}, params={"query": query, "per_page": min(limit, 80)}, timeout=20
    )
    resp.raise_for_status()
    data = resp.json()

    results = []
    if media_type == "video":
        for v in data.get("videos", []):
            files = sorted(v.get("video_files", []), key=lambda f: f.get("height") or 0, reverse=True)
            if not files:
                continue
            best = files[0]
            results.append(
                {
                    "id": v["id"],
                    "download_url": best["link"],
                    "width": best.get("width"),
                    "height": best.get("height"),
                    "page_url": v.get("url"),
                    "ext": ".mp4",
                }
            )
    else:
        for p in data.get("photos", []):
            src = p.get("src", {})
            results.append(
                {
                    "id": p["id"],
                    "download_url": src.get("original") or src.get("large"),
                    "width": p.get("width"),
                    "height": p.get("height"),
                    "page_url": p.get("url"),
                    "ext": ".jpg",
                }
            )
    return results


def search_pixabay(query, media_type, limit, key):
    import requests

    url = "https://pixabay.com/api/videos/" if media_type == "video" else "https://pixabay.com/api/"
    resp = requests.get(url, params={"key": key, "q": query, "per_page": min(max(limit, 3), 200)}, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    results = []
    if media_type == "video":
        for hit in data.get("hits", [])[:limit]:
            videos = hit.get("videos", {})
            best = videos.get("large") or videos.get("medium") or next(iter(videos.values()), None)
            if not best:
                continue
            results.append(
                {
                    "id": hit["id"],
                    "download_url": best["url"],
                    "width": best.get("width"),
                    "height": best.get("height"),
                    "page_url": hit.get("pageURL"),
                    "ext": ".mp4",
                }
            )
    else:
        for hit in data.get("hits", [])[:limit]:
            results.append(
                {
                    "id": hit["id"],
                    "download_url": hit.get("largeImageURL") or hit.get("webformatURL"),
                    "width": hit.get("imageWidth"),
                    "height": hit.get("imageHeight"),
                    "page_url": hit.get("pageURL"),
                    "ext": ".jpg",
                }
            )
    return results


def search_giphy(query, media_type, limit, key):
    import requests

    resp = requests.get(
        "https://api.giphy.com/v1/gifs/search",
        params={"api_key": key, "q": query, "limit": limit},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("data", []):
        images = item.get("images", {})
        original = images.get("original", {})
        if not original.get("url"):
            continue
        results.append(
            {
                "id": item["id"],
                "download_url": original["url"],
                "width": int(original["width"]) if original.get("width") else None,
                "height": int(original["height"]) if original.get("height") else None,
                "page_url": item.get("url"),
                "ext": ".gif",
            }
        )
    return results


SEARCHERS = {"pexels": search_pexels, "pixabay": search_pixabay, "giphy": search_giphy}


def download(url, dest_path):
    import requests

    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            f.write(chunk)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", required=True, choices=list(PROVIDERS))
    parser.add_argument("--query", required=True)
    parser.add_argument("--type", choices=["video", "image"], default="video")
    parser.add_argument("--out-dir", required=True, help="usually <media_library_path>/_stock_cache")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()

    if args.provider == "giphy" and args.type == "video":
        args.type = "image"  # giphy results are gifs regardless; keep the --type flag simple

    key = require_key(args.provider)

    try:
        import requests  # noqa: F401
    except ImportError:
        print("The `requests` package is required: pip3 install requests", file=sys.stderr)
        sys.exit(1)

    print(f"Searching {args.provider} for '{args.query}' ({args.type})...", file=sys.stderr)
    results = SEARCHERS[args.provider](args.query, args.type, args.limit, key)
    if not results:
        print("No results.", file=sys.stderr)
        sys.exit(0)

    provider_dir = os.path.join(args.out_dir, args.provider)
    os.makedirs(provider_dir, exist_ok=True)

    downloaded = []
    for r in results:
        if not r.get("download_url"):
            continue
        # `r["id"]` comes straight from the provider's JSON response, same as `download_url` —
        # slugify() it same as the (user-controlled but already-sanitized) query, rather than
        # trusting it to always be a bare integer, so a path-separator/traversal character in an
        # unexpected id shape from a future provider (or a compromised/spoofed response) can't
        # land outside provider_dir via os.path.join.
        filename = f"{slugify(args.query)}-{slugify(str(r['id']), max_len=40)}{r['ext']}"
        dest_path = os.path.join(provider_dir, filename)
        try:
            download(r["download_url"], dest_path)
        except Exception as e:  # noqa: BLE001 — one bad download shouldn't abort the batch
            print(f"WARNING: failed to download {r['download_url']}: {e}", file=sys.stderr)
            continue

        sidecar = {
            "provider": args.provider,
            "query": args.query,
            "source_page_url": r.get("page_url"),
            "license_note": PROVIDERS[args.provider]["license_note"],
            "width": r.get("width"),
            "height": r.get("height"),
        }
        with open(dest_path + ".stock.json", "w", encoding="utf-8") as f:
            json.dump(sidecar, f, ensure_ascii=False, indent=2)

        downloaded.append(dest_path)
        print(f"  downloaded {dest_path}", file=sys.stderr)

    print(json.dumps({"downloaded": downloaded}, ensure_ascii=False))
    if args.provider == "giphy":
        print(f"NOTE: {PROVIDERS['giphy']['license_note']}", file=sys.stderr)


if __name__ == "__main__":
    main()
