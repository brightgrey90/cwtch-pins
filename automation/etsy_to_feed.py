#!/usr/bin/env python3
"""Checks the shop for new Etsy listings and adds them to an RSS feed Zapier can pin.

The first run only records what is already listed, so existing listings are not pinned again.
Standard library only. Needs ETSY_API_KEY set as keystring:sharedsecret.
"""
import html, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from email.utils import formatdate
from pathlib import Path
from xml.sax.saxutils import escape

API = os.environ.get("ETSY_API_BASE", "https://api.etsy.com/v3/application")
SHOP = os.environ.get("ETSY_SHOP_NAME", "CwtchandClick3D")
SITE = os.environ.get("FEED_SITE", "https://brightgrey90.github.io/cwtch-pins")
ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parent.parent))
SEEN = ROOT / "automation" / "seen.json"
ITEMS = ROOT / "automation" / "feed-items.json"
FEED = ROOT / "feed" / "new-listings.xml"
FEED_SIZE = 30
FOOTER = os.environ.get("PIN_FOOTER", "Made in North Wales by CwtchAndClick3D.")


def get(path, params=None):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"x-api-key": os.environ["ETSY_API_KEY"], "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return json.load(res)
        except urllib.error.HTTPError as err:
            if err.code < 500 and err.code != 429:
                sys.exit(f"Etsy refused the request (HTTP {err.code}). Check the ETSY_API_KEY secret.")
            if attempt == 2:
                sys.exit(f"Etsy kept failing (HTTP {err.code}). Will try again next run.")
        except urllib.error.URLError as err:
            if attempt == 2:
                sys.exit(f"Could not reach Etsy ({err.reason}). Will try again next run.")
        time.sleep(5 * (attempt + 1))


def shop_id():
    found = get("/shops", {"shop_name": SHOP})
    for shop in found.get("results", []):
        if shop.get("shop_name", "").lower() == SHOP.lower():
            return shop["shop_id"]
    sys.exit(f"Could not find the Etsy shop {SHOP}.")


def active_listings(sid):
    listings, offset = [], 0
    while True:
        page = get(f"/shops/{sid}/listings/active", {"limit": 100, "offset": offset, "includes": "Images", "sort_on": "created", "sort_order": "desc"})
        batch = page.get("results", [])
        listings += batch
        offset += len(batch)
        if not batch or offset >= page.get("count", 0):
            return listings


def pin_title(title):
    title = re.sub(r"\s+", " ", html.unescape(title or "")).strip()
    if len(title) <= 100:
        return title
    out = ""
    for part in re.split(r"(\s\|\s|,\s)", title):
        if len(out + part) > 100:
            break
        out += part
    out = re.sub(r"(\s\|\s|,\s)$", "", out).strip()
    return out if len(out) >= 20 else title[:100].rsplit(" ", 1)[0]


def pin_description(listing):
    text = re.sub(r"\s+", " ", html.unescape(listing.get("description") or "")).strip()
    room = 495 - len(FOOTER)
    if len(text) > room:
        text = text[:room].rsplit(" ", 1)[0] + "…"
    return f"{text} {FOOTER}".strip()


def image_url(listing):
    images = sorted(listing.get("images") or [], key=lambda i: i.get("rank", 99))
    return images[0].get("url_fullxfull") if images else None


def to_item(listing):
    lid = str(listing["listing_id"])
    query = urllib.parse.urlencode({"utm_source": "pinterest", "utm_medium": "social", "utm_campaign": "auto-new", "utm_content": f"a{lid}"})
    return {
        "id": lid, "title": pin_title(listing.get("title")), "description": pin_description(listing),
        "link": f"https://www.etsy.com/uk/listing/{lid}?{query}", "image": image_url(listing),
        "date": int(listing.get("original_creation_timestamp") or listing.get("created_timestamp") or time.time()),
    }


def write_feed(items):
    FEED.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(
        f"""    <item>
      <title>{escape(i['title'])}</title>
      <link>{escape(i['link'])}</link>
      <guid isPermaLink="false">etsy-{i['id']}</guid>
      <pubDate>{formatdate(i['date'], usegmt=True)}</pubDate>
      <description>{escape(i['description'])}</description>
      <enclosure url="{escape(i['image'], {'"': '&quot;'})}" type="image/jpeg" length="0"/>
    </item>
"""
        for i in items
    )
    FEED.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>CwtchAndClick3D new listings</title>
    <link>{escape(SITE)}</link>
    <description>New listings from CwtchAndClick3D on Etsy</description>
{body}  </channel>
</rss>
""",
        encoding="utf-8",
    )


def main():
    if not os.environ.get("ETSY_API_KEY"):
        sys.exit("ETSY_API_KEY is not set. Add it under the repo's Settings, Secrets and variables, Actions.")
    listings = active_listings(shop_id())
    current = {str(l["listing_id"]) for l in listings}
    first_run = not SEEN.exists()
    seen = set(json.loads(SEEN.read_text())) if not first_run else set()
    items = json.loads(ITEMS.read_text()) if ITEMS.exists() else []
    added = []
    if first_run:
        print(f"First run: recorded {len(current)} existing listings. Nothing pinned.")
    else:
        fresh = sorted((l for l in listings if str(l["listing_id"]) not in seen), key=lambda l: l.get("created_timestamp", 0))
        known_ids = {i["id"] for i in items}
        for listing in fresh:
            item = to_item(listing)
            if not item["image"]:
                print(f"Skipped {item['id']}: no photo yet. Will retry next run.")
                current.discard(item["id"])
                continue
            if item["id"] not in known_ids:
                added.append(item)
        print(f"{len(added)} new listing(s) added to the feed.")
    items = sorted(items + added, key=lambda i: i["date"], reverse=True)[:FEED_SIZE]
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    SEEN.write_text(json.dumps(sorted(seen | current), indent=0))
    ITEMS.write_text(json.dumps(items, indent=1, ensure_ascii=False))
    write_feed(items)


if __name__ == "__main__":
    main()
