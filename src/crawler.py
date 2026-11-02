
import json
import re
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config" / "sites.json"
FEEDS_DIR = ROOT / "feeds"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    )
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def is_mainline_site(site):
    url = site.get("url", "")
    return "news.pokemon-home.com" in urlparse(url).netloc


def inspect_mainline_scripts(page_url, html):
    print("\n===== 본가 뉴스 JavaScript 분석 =====", flush=True)

    soup = BeautifulSoup(html, "html.parser")

    # 페이지 HTML에 선언된 실제 JavaScript 경로를 읽는다.
    script_urls = []

    for script in soup.find_all("script", src=True):
        script_url = urljoin(page_url, script["src"])

        if "resources/js/" in script_url:
            script_urls.append(script_url)

    # HTML에서 경로를 찾지 못했을 때 사용할 기본 경로
    if not script_urls:
        script_urls = [
            urljoin(page_url, "../resources/js/app-config.js"),
            urljoin(page_url, "../resources/js/newsList-web_hm.js"),
        ]

    for script_url in dict.fromkeys(script_urls):
        print("\n파일 주소:", script_url, flush=True)

        try:
            response = SESSION.get(script_url, timeout=20)
            response.raise_for_status()

            content = response.text

            print("HTTP 상태 코드:", response.status_code)
            print("파일 크기:", len(content), "bytes")
            print("----- JavaScript 내용 시작 -----")
            print(content[:20000])
            print("----- JavaScript 내용 끝 -----")

        except requests.RequestException as error:
            print("JavaScript 읽기 오류:", error, flush=True)


def get_news_links(site, page_url, html):
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        title = anchor.get_text(" ", strip=True)

        if not href or not title:
            continue

        full_url = urljoin(page_url, href)

        if urlparse(full_url).scheme not in ("http", "https"):
            continue

        if is_mainline_site(site):
            # 본가 뉴스 페이지에서 확인된 링크만 우선 수집
            if re.search(r"/ko/page/\d+\.html$", urlparse(full_url).path):
                links.append({
                    "title": title,
                    "url": full_url
                })

        else:
            # Pokémon GO 뉴스 링크
            if (
                "pokemongo.com" in urlparse(full_url).netloc
                and re.search(r"/ko/news/[^/?#]+", full_url)
            ):
                links.append({
                    "title": title,
                    "url": full_url
                })

    # 중복 제거
    unique = []
    seen = set()

    for item in links:
        if item["url"] not in seen:
            seen.add(item["url"])
            unique.append(item)

    return unique


def fetch_site(site):
    name = site.get("name", "이름 없는 사이트")
    site_url = site.get("url", "")
    site_id = site.get("id", "")

    print(f"\n[{name}] 접속 시작", flush=True)
    print("사이트 ID:", site_id)
    print("주소:", site_url)

    try:
        response = SESSION.get(site_url, timeout=30)
        response.raise_for_status()

        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        title = soup.title.get_text(strip=True) if soup.title else ""

        print("HTTP 상태 코드:", response.status_code)
        print("HTML 크기:", len(html), "bytes")
        print("페이지 제목:", title)

        # 본가 뉴스는 JavaScript로 목록을 구성하므로
        # HTML에 선언된 실제 스크립트 주소부터 분석한다.
        if is_mainline_site(site):
            inspect_mainline_scripts(site_url, html)

        links = get_news_links(site, site_url, html)

        print("페이지에서 발견한 전체 링크:", len(links))

        max_items = int(site.get("max_items", 30))
        links = links[:max_items]

        print(f"[{name}] 최종 수집:", len(links))

        return links

    except requests.RequestException as error:
        print(f"[오류] {name}: {error}", flush=True)
        return []


def make_rss(site, items):
    site_id = site.get("id", "feed")
    site_name = site.get("name", site_id)
    site_url = site.get("url", "")

    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = site_name
    SubElement(channel, "link").text = site_url
    SubElement(channel, "description").text = f"{site_name} RSS 피드"
    SubElement(channel, "language").text = "ko"

    SubElement(channel, "lastBuildDate").text = datetime.now(
        timezone.utc
    ).strftime("%a, %d %b %Y %H:%M:%S GMT")

    for item in items:
        entry = SubElement(channel, "item")

        SubElement(entry, "title").text = item["title"]
        SubElement(entry, "link").text = item["url"]
        SubElement(entry, "guid", isPermaLink="true").text = item["url"]
        SubElement(entry, "description").text = item["title"]

    output_file = FEEDS_DIR / f"{site_id}.xml"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    tree = ElementTree(rss)
    tree.write(
        output_file,
        encoding="utf-8",
        xml_declaration=True
    )

    print(f"[완료] {site_name}: {len(items)}개 뉴스 저장")
    print("RSS 파일:", output_file)


def main():
    print("================================")
    print("RSS 크롤러 실행")
    print("================================")

    config = load_config()
    sites = config.get("sites", [])

    print("등록된 사이트:", len(sites))

    FEEDS_DIR.mkdir(parents=True, exist_ok=True)

    for site in sites:
        if not site.get("enabled", True):
            print(f"[건너뜀] {site.get('name')} - 비활성화")
            continue

        items = fetch_site(site)
        make_rss(site, items)

    print("================================")
    print("RSS 크롤러 실행 종료")
    print("================================")


if __name__ == "__main__":
    print("===== CRAWLER START =====", flush=True)
    main()
