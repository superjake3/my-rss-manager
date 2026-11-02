
import json
import re
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
    return "news.pokemon-home.com" in urlparse(
        site.get("url", "")
    ).netloc


def fetch_mainline_json(site):
    page_url = site.get("url", "")

    # JavaScript의 './json/list.json' 경로를 기준으로 계산
    json_url = urljoin(page_url, "./json/list.json")

    print("\n===== 본가 뉴스 JSON 수집 =====", flush=True)
    print("JSON 주소:", json_url, flush=True)

    try:
        response = SESSION.get(json_url, timeout=30)

        print("HTTP 상태 코드:", response.status_code)
        print("응답 크기:", len(response.content), "bytes")

        response.raise_for_status()

        data = response.json()

        print("JSON 최상위 자료형:", type(data).__name__)

        if isinstance(data, dict):
            print("JSON 최상위 키:", list(data.keys()))

        # JavaScript에서 App.init(response.data)를 호출하는 구조
        items = data.get("data", []) if isinstance(data, dict) else data

        if not isinstance(items, list):
            print("뉴스 목록이 배열 형태가 아닙니다.")
            print("응답 일부:", str(data)[:5000])
            return []

        print("JSON 뉴스 항목 수:", len(items))

        if items:
            print("첫 번째 뉴스 항목의 필드:", list(items[0].keys()))
            print("첫 번째 뉴스 항목:")
            print(json.dumps(items[0], ensure_ascii=False, indent=2)[:5000])

        results = []

        for item in items:
            if not isinstance(item, dict):
                continue

            title = str(item.get("title", "")).strip()
            link = str(item.get("link", "")).strip()

            if not title or not link:
                continue

            full_url = urljoin(page_url, link)

            if urlparse(full_url).scheme not in ("http", "https"):
                continue

            results.append({
                "title": title,
                "url": full_url,
                "date": item.get("stAt", ""),
                "description": item.get("kindTxt", "")
            })

        # 최신순 정렬: 원본 데이터의 stAt 값은 Unix timestamp(초)
        results.sort(
            key=lambda x: int(x["date"]) if str(x["date"]).isdigit() else 0,
            reverse=True
        )

        max_items = int(site.get("max_items", 30))
        results = results[:max_items]

        print("최종 수집 뉴스:", len(results))

        return results

    except requests.RequestException as error:
        print("[JSON 요청 오류]", error, flush=True)
        return []

    except (ValueError, TypeError, KeyError) as error:
        print("[JSON 분석 오류]", error, flush=True)
        return []


def fetch_go_news(site):
    name = site.get("name", "Pokemon GO")
    page_url = site.get("url", "")

    print(f"\n[{name}] 접속 시작", flush=True)
    print("사이트 ID:", site.get("id", ""))
    print("주소:", page_url)

    try:
        response = SESSION.get(page_url, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        print("HTTP 상태 코드:", response.status_code)
        print("HTML 크기:", len(response.content), "bytes")
        print(
            "페이지 제목:",
            soup.title.get_text(strip=True) if soup.title else ""
        )

        results = []
        seen = set()

        for anchor in soup.find_all("a", href=True):
            title = anchor.get_text(" ", strip=True)
            href = anchor["href"].strip()

            if not title or not href:
                continue

            full_url = urljoin(page_url, href)

            if (
                "pokemongo.com" not in urlparse(full_url).netloc
                or not re.search(r"/ko/news/[^/?#]+", full_url)
            ):
                continue

            if full_url in seen:
                continue

            seen.add(full_url)

            results.append({
                "title": title,
                "url": full_url,
                "date": "",
                "description": ""
            })

        max_items = int(site.get("max_items", 30))
        results = results[:max_items]

        print("페이지에서 발견한 전체 링크:", len(seen))
        print(f"[{name}] 최종 수집:", len(results))

        return results

    except requests.RequestException as error:
        print("[오류]", error, flush=True)
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

        description = item.get("description", "")
        SubElement(entry, "description").text = description or item["title"]

        timestamp = item.get("date", "")

        if str(timestamp).isdigit():
            try:
                pub_date = datetime.fromtimestamp(
                    int(timestamp),
                    timezone.utc
                ).strftime("%a, %d %b %Y %H:%M:%S GMT")

                SubElement(entry, "pubDate").text = pub_date
            except (ValueError, OverflowError):
                pass

    FEEDS_DIR.mkdir(parents=True, exist_ok=True)

    output_file = FEEDS_DIR / f"{site_id}.xml"

    ElementTree(rss).write(
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

        if is_mainline_site(site):
            print(f"\n[{site.get('name')}] 접속 시작")
            items = fetch_mainline_json(site)
        else:
            items = fetch_go_news(site)

        make_rss(site, items)

    print("================================")
    print("RSS 크롤러 실행 종료")
    print("================================")


if __name__ == "__main__":
    print("===== CRAWLER START =====", flush=True)
    main()
