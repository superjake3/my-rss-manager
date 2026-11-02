
import json
import hashlib
import re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree

import requests
from bs4 import BeautifulSoup


# ==========================================
# 기본 설정
# ==========================================

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


# ==========================================
# 사이트별 뉴스 주소 규칙
# ==========================================

def get_news_url_rule(site_id, url):

    parsed = urlparse(url)
    path = parsed.path

    # 포켓몬 GO
    if site_id == "pokemon-go":
        return bool(
            re.search(r"/ko/news/[^/?#]+", path)
        )

    # 포켓몬 본가 소식
    # 기존 ID pokemon-home도 지원
    elif site_id in ("pokemon-mainline", "pokemon-home"):
        return bool(
            re.search(r"/ko/page/\d+\.html$", path)
        )

    return False


# ==========================================
# 뉴스 수집
# ==========================================

def fetch_site(site):

    site_id = site["id"]
    site_url = site["url"]

    print(f"\n[{site['name']}] 접속 시작", flush=True)
    print(f"주소: {site_url}", flush=True)

    response = requests.get(
        site_url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    print(
        f"HTTP 상태 코드: {response.status_code}",
        flush=True
    )

    print(
        f"HTML 크기: {len(response.text)} bytes",
        flush=True
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # 페이지 제목
    page_title = (
        soup.title.get_text(strip=True)
        if soup.title
        else "없음"
    )

    print(f"페이지 제목: {page_title}", flush=True)

    # JavaScript 파일 주소 확인
    print("\n=== JavaScript 파일 주소 ===", flush=True)

    scripts = soup.find_all("script", src=True)

    if scripts:
        for script in scripts:
            script_url = urljoin(
                site_url,
                script["src"]
            )
            print(script_url, flush=True)
    else:
        print("외부 JavaScript 파일을 찾지 못했습니다.", flush=True)

    # HTML 일부 확인
    print("\n=== HTML 내용 일부 ===", flush=True)
    print(response.text[:1800], flush=True)

    # 뉴스 링크 수집
    items = []
    seen = set()

    links = soup.find_all(
        "a",
        href=True
    )

    print(
        f"\n페이지에서 발견한 전체 링크: {len(links)}개",
        flush=True
    )

    for link in links:

        raw_url = link.get("href", "").strip()

        if not raw_url:
            continue

        article_url = urljoin(
            site_url,
            raw_url
        )

        # 사이트별 뉴스 주소 확인
        if not get_news_url_rule(
            site_id,
            article_url
        ):
            continue

        # 제목 추출
        title = link.get_text(
            " ",
            strip=True
        )

        if not title:
            title = link.get(
                "aria-label",
                ""
            ).strip()

        if not title:
            title = link.get(
                "title",
                ""
            ).strip()

        if not title:
            continue

        # 중복 제거
        if article_url in seen:
            continue

        seen.add(article_url)

        items.append({
            "title": title,
            "url": article_url
        })

    # 최대 수집 개수 제한
    max_items = int(
        site.get("max_items", 30)
    )

    items = items[:max_items]

    print(
        f"[{site['name']}] 최종 수집: {len(items)}개",
        flush=True
    )

    if len(items) == 0:
        print(
            "뉴스를 찾지 못했습니다. "
            "페이지 구조 또는 API 확인이 필요합니다.",
            flush=True
        )

    return items


# ==========================================
# RSS XML 생성
# ==========================================

def make_feed(site, items):

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
    ).text = (
        site["name"] + " RSS Feed"
    )

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


# ==========================================
# 전체 실행
# ==========================================

def main():

    print("================================", flush=True)
    print("RSS 크롤러 실행", flush=True)
    print("================================", flush=True)

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

    print(
        f"등록된 사이트: {len(sites)}개",
        flush=True
    )

    # 등록된 사이트 순회
    for site in sites:

        if not site.get("enabled", True):

            print(
                f"[건너뜀] {site.get('name', '이름 없음')}",
                flush=True
            )

            continue

        try:

            items = fetch_site(site)

            rss = make_feed(
                site,
                items
            )

            output = FEEDS / f'{site["id"]}.xml'

            ElementTree(rss).write(
                output,
                encoding="utf-8",
                xml_declaration=True
            )

            print(
                f"[완료] {site['name']}: "
                f"{len(items)}개 뉴스 저장",
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


# ==========================================
# 프로그램 시작점
# ==========================================

if __name__ == "__main__":
    print("===== CRAWLER START =====", flush=True)
    main()
