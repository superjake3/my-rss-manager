
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
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9"
}


def is_mainline_site(site):
    """사이트 ID와 관계없이 본가 뉴스 사이트인지 확인"""

    return "news.pokemon-home.com" in site.get("url", "")


def get_news_url_rule(site, url):

    parsed = urlparse(url)
    path = parsed.path

    site_id = site.get("id", "")

    if site_id == "pokemon-go":
        return bool(
            re.search(r"/ko/news/[^/?#]+", path)
        )

    if is_mainline_site(site):
        return bool(
            re.search(r"/ko/page/\d+\.html$", path)
        )

    return False


def inspect_mainline_scripts(site_url):

    print("\n===== 본가 뉴스 JavaScript 분석 =====", flush=True)

    js_files = [
        "resources/js/app-config.js",
        "resources/js/newsList-web_hm.js"
    ]

    for js_file in js_files:

        js_url = urljoin(site_url, js_file)

        print(f"\n파일 주소: {js_url}", flush=True)

        try:

            response = requests.get(
                js_url,
                headers=HEADERS,
                timeout=30
            )

            response.raise_for_status()

            content = response.text

            print(
                f"파일 크기: {len(content)} bytes",
                flush=True
            )

            print("===== 파일 내용 시작 =====", flush=True)
            print(content[:15000], flush=True)
            print("===== 파일 내용 종료 =====", flush=True)

        except Exception as error:

            print(
                f"JavaScript 읽기 오류: {type(error).__name__} - {error}",
                flush=True
            )


def fetch_site(site):

    site_url = site["url"]

    print(f"\n[{site['name']}] 접속 시작", flush=True)
    print(f"사이트 ID: {site.get('id')}", flush=True)
    print(f"주소: {site_url}", flush=True)

    response = requests.get(
        site_url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    print(f"HTTP 상태 코드: {response.status_code}", flush=True)
    print(f"HTML 크기: {len(response.text)} bytes", flush=True)

    soup = BeautifulSoup(response.text, "html.parser")

    page_title = (
        soup.title.get_text(strip=True)
        if soup.title else "없음"
    )

    print(f"페이지 제목: {page_title}", flush=True)

    # 사이트 ID가 아니라 실제 주소로 판단
    if is_mainline_site(site):
        inspect_mainline_scripts(site_url)

    links = soup.find_all("a", href=True)

    print(
        f"페이지에서 발견한 전체 링크: {len(links)}개",
        flush=True
    )

    items = []
    seen = set()

    for link in links:

        raw_url = link.get("href", "").strip()

        if not raw_url:
            continue

        article_url = urljoin(site_url, raw_url)

        if not get_news_url_rule(site, article_url):
            continue

        title = link.get_text(" ", strip=True)

        if not title:
            title = link.get("aria-label", "").strip()

        if not title:
            title = link.get("title", "").strip()

        if not title or article_url in seen:
            continue

        seen.add(article_url)

        items.append({
            "title": title,
            "url": article_url
        })

    max_items = int(site.get("max_items", 30))
    items = items[:max_items]

    print(
        f"[{site['name']}] 최종 수집: {len(items)}개",
        flush=True
    )

    return items


def make_feed(site, items):

    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = site["name"]
    SubElement(channel, "link").text = site["url"]
    SubElement(channel, "description").text = site["name"] + " RSS Feed"

    for item in items:

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

    print("================================", flush=True)
    print("RSS 크롤러 실행", flush=True)
    print("================================", flush=True)

    if not CONFIG.exists():
        raise FileNotFoundError(f"설정 파일 없음: {CONFIG}")

    with open(CONFIG, "r", encoding="utf-8") as file:
        config = json.load(file)

    sites = config.get("sites", [])

    print(f"등록된 사이트: {len(sites)}개", flush=True)

    for site in sites:

        if not site.get("enabled", True):
            print(f"[건너뜀] {site['name']}", flush=True)
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
                f"[완료] {site['name']}: {len(items)}개 뉴스 저장",
                flush=True
            )

        except Exception as error:

            print(
                f"[오류] {site.get('name', '이름 없음')}: "
                f"{type(error).__name__} - {error}",
                flush=True
            )

    print("================================", flush=True)
    print("RSS 크롤러 실행 종료", flush=True)
    print("================================", flush=True)


if __name__ == "__main__":
    print("===== CRAWLER START =====", flush=True)
    main()
