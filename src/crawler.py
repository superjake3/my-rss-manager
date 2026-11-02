
import json
import hashlib
import re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree

import requests
from bs4 import BeautifulSoup


# 기본 경로
ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "sites.json"
FEEDS = ROOT / "feeds"

FEEDS.mkdir(exist_ok=True)

# 웹사이트 접속 정보
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9"
}


def get_news_url_rule(site_id, url):
    """
    사이트별 뉴스 게시물 주소인지 확인
    """

    parsed = urlparse(url)
    path = parsed.path

    if site_id == "pokemon-go":
        return bool(
            re.search(r"/ko/news/[^/?#]+", path)
        )

    elif site_id == "pokemon-home":
        return bool(
            re.search(r"/ko/page/\d+\.html$", path)
        )

    # 아직 규칙이 없는 사이트
    return False


def fetch_site(site):
    """
    사이트에 접속해 뉴스 제목과 링크 수집
    """

    site_id = site["id"]
    site_url = site["url"]

    print(f"\n[{site['name']}] 접속 시작")
    print(f"주소: {site_url}")

    response = requests.get(
        site_url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    print(f"HTTP 상태 코드: {response.status_code}")
    print(f"HTML 크기: {len(response.text)} bytes")

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    items = []
    seen = set()

    links = soup.find_all("a", href=True)

    print(f"페이지에서 발견한 전체 링크: {len(links)}개")

    for link in links:

        raw_url = link.get("href", "").strip()

        if not raw_url:
            continue

        # 상대 주소를 전체 주소로 변환
        article_url = urljoin(site_url, raw_url)

        parsed = urlparse(article_url)

        # 사이트별 뉴스 주소 확인
        if not get_news_url_rule(site_id, article_url):
            continue

        # 제목 추출
        title = link.get_text(" ", strip=True)

        if not title:
            title = link.get("aria-label", "").strip()

        if not title:
            title = link.get("title", "").strip()

        # 제목이 없는 링크 제외
        if not title:
            continue

        # 중복 링크 제외
        if article_url in seen:
            continue

        seen.add(article_url)

        items.append({
            "title": title,
            "url": article_url
        })

    # 최대 수집 개수 적용
    max_items = int(site.get("max_items", 30))
    items = items[:max_items]

    print(f"[{site['name']}] 최종 수집: {len(items)}개")

    if len(items) == 0:
        print(
            "뉴스를 찾지 못했습니다. "
            "페이지가 자바스크립트로 구성되어 있거나 "
            "뉴스 주소 규칙이 다를 수 있습니다."
        )

    return items


def make_feed(site, items):
    """
    수집한 뉴스로 RSS XML 생성
    """

    rss = Element(
        "rss",
        version="2.0"
    )

    channel = SubElement(
        rss,
        "channel"
    )

    SubElement(
        channel,
        "title"
    ).text = site["name"]

    SubElement(
        channel,
        "link"
    ).text = site["url"]

    SubElement(
        channel,
        "description"
    ).text = site["name"] + " RSS Feed"

    for item in items:

        entry = SubElement(
            channel,
            "item"
        )

        SubElement(
            entry,
            "title"
        ).text = item["title"]

        SubElement(
            entry,
            "link"
        ).text = item["url"]

        guid = hashlib.sha256(
            item["url"].encode("utf-8")
        ).hexdigest()

        SubElement(
            entry,
            "guid"
        ).text = guid

    SubElement(
        channel,
        "lastBuildDate"
    ).text = datetime.now(
        timezone.utc
    ).strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )

    return rss


def main():

    print("================================")
    print("RSS 크롤러 실행")
    print("================================")

    # 설정 파일 확인
    if not CONFIG.exists():
        raise FileNotFoundError(
            f"설정 파일을 찾을 수 없습니다: {CONFIG}"
        )

    with open(
        CONFIG,
        "r",
        encoding="utf-8"
    ) as file:
        config = json.load(file)

    sites = config.get("sites", [])

    print(f"등록된 사이트: {len(sites)}개")

    for site in sites:

        if not site.get("enabled", True):
            print(
                f"[건너뜀] {site.get('name', '이름 없음')}"
            )
            continue

        try:

            items = fetch_site(site)

            rss = make_feed(
                site,
                items
            )

            output = FEEDS / f"{site['id']}.xml"

            ElementTree(rss).write(
                output,
                encoding="utf-8",
                xml_declaration=True
            )

            print(
                f"[완료] {site['name']}: "
                f"{len(items)}개 뉴스 저장"
            )

        except Exception as error:

            print(
                f"[오류] {site.get('name', '이름 없음')}: "
                f"{type(error).__name__} - {error}"
            )

    print("================================")
    print("RSS 크롤러 실행 종료")
    print("================================")


if __name__ == "__main__":
    main()
