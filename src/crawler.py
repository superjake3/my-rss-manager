
import json
import hashlib
import re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "sites.json"
FEEDS = ROOT / "feeds"

FEEDS.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9"
}


def fetch_site(site):
    response = requests.get(
        site["url"],
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    items = []
    seen = set()

    for link in soup.find_all("a", href=True):
        url = urljoin(site["url"], link["href"])
        parsed = urlparse(url)

       # 사이트별 뉴스 주소 규칙
site_id = site["id"]

if site_id == "pokemon-go":
    is_news = bool(
        re.search(r"/ko/news/[^/?#]+", parsed.path)
    )

elif site_id == "pokemon-home":
    is_news = bool(
        re.search(r"/ko/page/\d+\.html", parsed.path)
    )

else:
    is_news = False

if not is_news:
    continue

        title = link.get_text(" ", strip=True)

        if not title:
            title = link.get("aria-label", "").strip()

        if not title:
            title = link.get("title", "").strip()

        if not title or url in seen:
            continue

        seen.add(url)

        items.append({
            "title": title,
            "url": url
        })

    print(f"발견한 뉴스 링크: {len(items)}개")

    return items


def make_feed(site, items):
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = site["name"]
    SubElement(channel, "link").text = site["url"]
    SubElement(channel, "description").text = (
        site["name"] + " RSS Feed"
    )

    for item in items[:site.get("max_items", 30)]:
        entry = SubElement(channel, "item")

        SubElement(entry, "title").text = item["title"]
        SubElement(entry, "link").text = item["url"]

        guid = hashlib.sha256(
            item["url"].encode("utf-8")
        ).hexdigest()

        SubElement(entry, "guid").text = guid

    SubElement(channel, "lastBuildDate").text = (
        datetime.now(timezone.utc).strftime(
            "%a, %d %b %Y %H:%M:%S +0000"
        )
    )

    return rss


def main():
    with open(CONFIG, encoding="utf-8") as file:
        config = json.load(file)

    for site in config["sites"]:
        if not site.get("enabled", True):
            continue

        try:
            items = fetch_site(site)
            rss = make_feed(site, items)

            output = FEEDS / f'{site["id"]}.xml'

            ElementTree(rss).write(
                output,
                encoding="utf-8",
                xml_declaration=True
            )

            print(
                f'{site["name"]}: {len(items)} items collected'
            )

        except Exception as error:
            print(
                f'{site["name"]}: ERROR - {error}'
            )


if __name__ == "__main__":
    main()
