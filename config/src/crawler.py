
import json
import hashlib
import re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
import feedparser
from bs4 import BeautifulSoup
from xml.etree.ElementTree import Element, SubElement, ElementTree

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "sites.json"
FEEDS = ROOT / "feeds"

FEEDS.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MyRSSManager/1.0)"
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

    for article in soup.select("article, .news-item, .post"):
        link = article.find("a", href=True)
        if not link:
            continue

        title = article.get_text(" ", strip=True)

        if not title:
            continue

        url = urljoin(site["url"], link["href"])

        items.append({
            "title": title,
            "url": url
        })

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

        guid = hashlib.md5(
            item["url"].encode()
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
