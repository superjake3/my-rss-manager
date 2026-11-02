
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urlunparse
from xml.etree.ElementTree import (
    Element, SubElement, ElementTree, parse as parse_xml
)

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config" / "sites.json"
FEEDS_DIR = ROOT / "feeds"
STATE_DIR = FEEDS_DIR / ".state"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    )
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ========================================
# 기본 설정
# ========================================

def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def is_mainline_site(site):
    return "news.pokemon-home.com" in urlparse(
        site.get("url", "")
    ).netloc


def normalize_url(url):
    if not url:
        return ""

    parsed = urlparse(url.strip())

    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path.rstrip("/"),
        "",
        parsed.query,
        ""
    ))


def get_item_key(item):
    url = normalize_url(item.get("url", ""))

    if url:
        return f"url:{url}"

    source_id = str(item.get("source_id", "")).strip()

    if source_id:
        return f"id:{source_id}"

    return ""


def date_value(value):
    try:
        return int(value)
    except (ValueError, TypeError, OverflowError):
        return 0


# ========================================
# 기존 뉴스 기록 불러오기
# ========================================

def load_state(site):
    site_id = site.get("id", "feed")
    state_file = STATE_DIR / f"{site_id}.json"

    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as file:
                data = json.load(file)

            items = data.get("items", [])

            if isinstance(items, list):
                print(
                    f"[기존 기록] {site_id}: {len(items)}개",
                    flush=True
                )
                return items

        except (OSError, json.JSONDecodeError) as error:
            print("[기록 읽기 오류]", error, flush=True)

    # 상태 파일이 없으면 기존 RSS에서 복구
    rss_file = FEEDS_DIR / f"{site_id}.xml"

    if rss_file.exists():
        try:
            root = parse_xml(rss_file).getroot()
            restored = []

            for entry in root.findall("./channel/item"):
                title = entry.findtext("title", "")
                url = entry.findtext("link", "")

                if not title or not url:
                    continue

                restored.append({
                    "title": title,
                    "url": url,
                    "date": "",
                    "description": entry.findtext(
                        "description", ""
                    ),
                    "source_id": "",
                    "pub_date": entry.findtext("pubDate", "")
                })

            print(
                f"[기존 RSS 복구] {len(restored)}개",
                flush=True
            )

            return restored

        except Exception as error:
            print("[RSS 복구 오류]", error, flush=True)

    return []


def save_state(site, items):
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    state_file = STATE_DIR / f"{site.get('id', 'feed')}.json"
    temp_file = state_file.with_suffix(".tmp")

    data = {
        "site_id": site.get("id", "feed"),
        "site_name": site.get("name", ""),
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "items": items
    }

    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )

    temp_file.replace(state_file)

    print(f"[기록 저장] 전체 {len(items)}개 뉴스")


# ========================================
# 포켓몬 본가 뉴스 수집
# ========================================

def fetch_mainline_json(site):
    page_url = site.get("url", "")
    json_url = urljoin(page_url, "./json/list.json")

    print("\n===== 본가 뉴스 JSON 수집 =====", flush=True)
    print("JSON 주소:", json_url)

    try:
        response = SESSION.get(json_url, timeout=30)

        print("HTTP 상태 코드:", response.status_code)
        print("응답 크기:", len(response.content), "bytes")

        response.raise_for_status()

        data = response.json()
        items = data.get("data", []) if isinstance(data, dict) else data

        if not isinstance(items, list):
            print("[오류] 뉴스 목록이 배열이 아닙니다.")
            return None

        print("JSON 뉴스 항목 수:", len(items))

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
                "description": item.get("kindTxt", ""),
                "source_id": str(item.get("id", "")),
                "pub_date": ""
            })

        results.sort(
            key=lambda item: date_value(item.get("date")),
            reverse=True
        )

        print("최종 수집 뉴스:", len(results))

        return results

    except requests.RequestException as error:
        print("[JSON 요청 오류]", error, flush=True)
        return None

    except (ValueError, TypeError, KeyError) as error:
        print("[JSON 분석 오류]", error, flush=True)
        return None


# ========================================
# Pokémon GO 뉴스 수집
# ========================================

def fetch_go_news(site):
    name = site.get("name", "Pokemon GO")
    page_url = site.get("url", "")

    print(f"\n[{name}] 접속 시작")
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

            key = normalize_url(full_url)

            if key in seen:
                continue

            seen.add(key)

            results.append({
                "title": title,
                "url": full_url,
                "date": "",
                "description": "",
                "source_id": "",
                "pub_date": ""
            })

        print("페이지에서 발견한 뉴스:", len(results))

        return results

    except requests.RequestException as error:
        print("[GO 뉴스 요청 오류]", error, flush=True)
        return None


# ========================================
# 기존 뉴스와 신규 뉴스 병합
# ========================================

def merge_news(old_items, new_items, site):
    """
    기존 기록과 새 수집 결과를 URL 기준으로 비교한다.

    기존 기록에 없는 뉴스만 신규로 집계한다.
    내부 기록은 전체 보관하고 RSS 출력 단계에서만
    max_items 제한을 적용한다.
    """

    merged = []
    known = {}
    new_count = 0
    duplicate_count = 0

    # 기존 기록을 먼저 등록
    for item in old_items:
        key = get_item_key(item)

        if not key:
            continue

        if key in known:
            continue

        known[key] = item
        merged.append(item)

    old_count = len(merged)

    # 새 수집 결과 비교
    for item in new_items:
        key = get_item_key(item)

        if not key:
            continue

        if key in known:
            duplicate_count += 1

            # 기존 뉴스의 제목이나 설명 등이 갱신된 경우 반영
            existing = known[key]

            for field, value in item.items():
                if value not in (None, ""):
                    existing[field] = value

            continue

        known[key] = item
        merged.append(item)
        new_count += 1

    # 본가 뉴스는 게시 날짜 최신순 정렬
    if is_mainline_site(site):
        merged.sort(
            key=lambda item: date_value(item.get("date")),
            reverse=True
        )

    print("--------------------------------")
    print("기존 기록:", old_count)
    print("이번 실행 신규 뉴스:", new_count)
    print("기존 기록과 중복:", duplicate_count)
    print("내부 전체 기록:", len(merged))
    print("--------------------------------")

    return merged, new_count, duplicate_count


# ========================================
# RSS 생성
# ========================================

def make_pub_date(item):
    existing = item.get("pub_date", "")

    if existing:
        return existing

    timestamp = date_value(item.get("date", ""))

    if timestamp:
        try:
            return datetime.fromtimestamp(
                timestamp,
                timezone.utc
            ).strftime("%a, %d %b %Y %H:%M:%S GMT")
        except (ValueError, OverflowError, OSError):
            pass

    return ""


def make_rss(site, all_items):
    site_id = site.get("id", "feed")
    site_name = site.get("name", site_id)
    site_url = site.get("url", "")

    max_items = max(1, int(site.get("max_items", 30)))

    # 내부 기록 전체가 아닌 RSS에는 최신 N개만 표시
    rss_items = all_items[:max_items]

    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = site_name
    SubElement(channel, "link").text = site_url
    SubElement(channel, "description").text = f"{site_name} RSS 피드"
    SubElement(channel, "language").text = "ko"

    SubElement(channel, "lastBuildDate").text = datetime.now(
        timezone.utc
    ).strftime("%a, %d %b %Y %H:%M:%S GMT")

    for item in rss_items:
        entry = SubElement(channel, "item")

        SubElement(entry, "title").text = item.get("title", "")
        SubElement(entry, "link").text = item.get("url", "")

        SubElement(
            entry,
            "guid",
            isPermaLink="true"
        ).text = item.get("url", "")

        description = item.get("description", "")

        SubElement(entry, "description").text = (
            description or item.get("title", "")
        )

        pub_date = make_pub_date(item)

        if pub_date:
            SubElement(entry, "pubDate").text = pub_date

    FEEDS_DIR.mkdir(parents=True, exist_ok=True)

    output_file = FEEDS_DIR / f"{site_id}.xml"
    temp_file = output_file.with_suffix(".tmp")

    ElementTree(rss).write(
        temp_file,
        encoding="utf-8",
        xml_declaration=True
    )

    temp_file.replace(output_file)

    print(f"[RSS 저장] {len(rss_items)}개")
    print("RSS 파일:", output_file)


# ========================================
# 메인 실행
# ========================================

def main():
    print("================================")
    print("RSS 크롤러 실행")
    print("================================")

    config = load_config()
    sites = config.get("sites", [])

    print("등록된 사이트:", len(sites))

    FEEDS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    for site in sites:
        if not site.get("enabled", True):
            print(f"[건너뜀] {site.get('name')} - 비활성화")
            continue

        site_name = site.get("name", site.get("id", "사이트"))

        print("\n================================")
        print(f"[시작] {site_name}")
        print("================================")

        if is_mainline_site(site):
            new_items = fetch_mainline_json(site)
        else:
            new_items = fetch_go_news(site)

        # 수집 실패 시 기존 RSS 및 기록 보존
        if new_items is None:
            print(
                f"[보존] {site_name}: 수집 실패. 기존 RSS 유지",
                flush=True
            )
            continue

        old_items = load_state(site)

        all_items, new_count, duplicate_count = merge_news(
            old_items,
            new_items,
            site
        )

        # 전체 기록 저장
        save_state(site, all_items)

        # RSS에는 설정된 개수만 표시
        make_rss(site, all_items)

        print(f"[신규 등록] {new_count}개")
        print(f"[중복 제외] {duplicate_count}개")
        print(f"[전체 기록] {len(all_items)}개")
        print(
            f"[RSS 표시] {min(len(all_items), int(site.get('max_items', 30)))}개"
        )

    print("\n================================")
    print("RSS 크롤러 실행 종료")
    print("================================")


if __name__ == "__main__":
    print("===== CRAWLER START =====", flush=True)
    main()
