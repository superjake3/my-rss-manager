
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urlunparse
from xml.etree.ElementTree import (
    Element,
    SubElement,
    ElementTree,
    parse as parse_xml
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
# 기본 설정 및 파일 관리
# ========================================

def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def is_mainline_site(site):
    return "news.pokemon-home.com" in urlparse(
        site.get("url", "")
    ).netloc


def get_state_file(site_id):
    return STATE_DIR / f"{site_id}.json"


def normalize_url(url):
    """
    URL의 불필요한 차이를 줄여 중복 판별에 사용한다.
    """
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
    """
    뉴스 고유 ID가 있으면 ID를 우선 사용하고,
    없으면 URL을 사용한다.
    """
    source_id = str(item.get("source_id", "")).strip()

    if source_id:
        return f"id:{source_id}"

    return f"url:{normalize_url(item.get('url', ''))}"


def load_state(site):
    """
    이전 실행에서 저장한 뉴스 목록을 불러온다.

    상태 파일이 없으면 기존 RSS XML을 읽어
    기존 뉴스 기록을 복구한다.
    """
    site_id = site.get("id", "feed")
    state_file = get_state_file(site_id)

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

    # 최초 실행 시 기존 RSS 파일에서 뉴스 복구
    rss_file = FEEDS_DIR / f"{site_id}.xml"

    if rss_file.exists():
        try:
            root = parse_xml(rss_file).getroot()
            restored = []

            for entry in root.findall("./channel/item"):
                title = entry.findtext("title", "")
                url = entry.findtext("link", "")
                description = entry.findtext("description", "")
                pub_date = entry.findtext("pubDate", "")

                if not title or not url:
                    continue

                restored.append({
                    "title": title,
                    "url": url,
                    "date": "",
                    "description": description,
                    "pub_date": pub_date,
                    "source_id": ""
                })

            print(
                f"[기존 RSS 복구] {len(restored)}개 뉴스",
                flush=True
            )

            return restored

        except Exception as error:
            print("[기존 RSS 복구 오류]", error, flush=True)

    return []


def save_state(site, items):
    """
    누적 뉴스 목록을 JSON으로 저장한다.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    state_file = get_state_file(site.get("id", "feed"))
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

    print(
        f"[기록 저장] {len(items)}개 뉴스",
        flush=True
    )


# ========================================
# 날짜 처리
# ========================================

def date_value(value):
    """
    숫자형 Unix timestamp를 정수로 변환한다.
    날짜가 없는 뉴스는 0으로 처리한다.
    """
    try:
        return int(value)
    except (ValueError, TypeError, OverflowError):
        return 0


def make_pub_date(item):
    """
    RSS pubDate 생성.
    기존 pubDate가 있으면 유지한다.
    """
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


# ========================================
# 포켓몬 본가 뉴스 수집
# ========================================

def fetch_mainline_json(site):
    page_url = site.get("url", "")
    json_url = urljoin(page_url, "./json/list.json")

    print("\n===== 본가 뉴스 JSON 수집 =====", flush=True)
    print("JSON 주소:", json_url, flush=True)

    try:
        response = SESSION.get(json_url, timeout=30)

        print("HTTP 상태 코드:", response.status_code)
        print("응답 크기:", len(response.content), "bytes")

        response.raise_for_status()

        data = response.json()

        items = data.get("data", []) if isinstance(data, dict) else data

        if not isinstance(items, list):
            print("[오류] 뉴스 목록이 배열 형태가 아닙니다.")
            return None

        print("JSON 뉴스 항목 수:", len(items))

        results = []

        for item in items:
            if not isinstance(item, dict):
                continue

            title = str(item.get("title", "")).strip()
            link = str(item.get("link", "")).strip()
            source_id = str(item.get("id", "")).strip()

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
                "source_id": source_id,
                "pub_date": ""
            })

        results.sort(
            key=lambda item: date_value(item.get("date")),
            reverse=True
        )

        print("최종 수집 뉴스:", len(results), flush=True)

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

            normalized = normalize_url(full_url)

            if normalized in seen:
                continue

            seen.add(normalized)

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
# 기존 뉴스 + 신규 뉴스 병합
# ========================================

def merge_news(old_items, new_items, site):
    """
    기존 뉴스와 신규 뉴스를 병합한다.

    중복 뉴스는 추가하지 않는다.
    신규 뉴스는 목록 앞쪽에 배치한다.
    본가 뉴스는 게시 날짜 최신순으로 정렬한다.
    """

    merged = []
    seen_keys = set()
    seen_urls = set()

    new_count = 0
    duplicate_count = 0

    # 신규 뉴스부터 등록
    for item in new_items:
        key = get_item_key(item)
        url_key = normalize_url(item.get("url", ""))

        if not url_key:
            continue

        if key in seen_keys or url_key in seen_urls:
            duplicate_count += 1
            continue

        seen_keys.add(key)
        seen_urls.add(url_key)

        merged.append(item)
        new_count += 1

    # 기존 뉴스 중 신규 목록에 없는 뉴스만 유지
    for item in old_items:
        key = get_item_key(item)
        url_key = normalize_url(item.get("url", ""))

        if not url_key:
            continue

        if key in seen_keys or url_key in seen_urls:
            continue

        seen_keys.add(key)
        seen_urls.add(url_key)

        merged.append(item)

    # 본가 뉴스는 날짜 기준 최신순 정렬
    if is_mainline_site(site):
        merged.sort(
            key=lambda item: date_value(item.get("date")),
            reverse=True
        )

    # 사이트별 보관 개수 적용
    max_items = max(1, int(site.get("max_items", 30)))

    merged = merged[:max_items]

    print("--------------------------------")
    print("이번 실행 신규 뉴스:", new_count)
    print("이번 실행 중복 뉴스:", duplicate_count)
    print("기존 뉴스 포함 누적:", len(merged))
    print("최대 보관 개수:", max_items)
    print("--------------------------------")

    return merged, new_count, duplicate_count


# ========================================
# RSS XML 생성
# ========================================

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

        SubElement(entry, "title").text = item.get("title", "")
        SubElement(entry, "link").text = item.get("url", "")

        # URL을 RSS 고유 식별자로 사용
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

    print(f"[완료] {site_name}: {len(items)}개 뉴스 저장")
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

        # 사이트별 뉴스 수집
        if is_mainline_site(site):
            new_items = fetch_mainline_json(site)
        else:
            new_items = fetch_go_news(site)

        # 수집 실패 시 기존 파일과 기록 보존
        if new_items is None:
            print(
                f"[보존] {site_name}: 수집 실패로 기존 RSS를 유지합니다.",
                flush=True
            )
            continue

        # 기존 뉴스 불러오기
        old_items = load_state(site)

        # 기존 뉴스와 신규 뉴스 병합
        merged_items, new_count, duplicate_count = merge_news(
            old_items,
            new_items,
            site
        )

        # RSS 및 누적 기록 저장
        make_rss(site, merged_items)
        save_state(site, merged_items)

        print(f"[신규 등록] {new_count}개")
        print(f"[중복 제외] {duplicate_count}개")
        print(f"[최종 보관] {len(merged_items)}개")

    print("\n================================")
    print("RSS 크롤러 실행 종료")
    print("================================")


if __name__ == "__main__":
    print("===== CRAWLER START =====", flush=True)
    main()
