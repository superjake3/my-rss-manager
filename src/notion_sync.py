
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "feeds" / ".state"
SYNC_FILE = STATE_DIR / "notion-sync.json"

DATA_SOURCE_ID = os.getenv("NOTION_DATA_SOURCE_ID", "").strip()
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "").strip()

NOTION_VERSION = "2026-03-11"
API_BASE = "https://api.notion.com/v1"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
    "User-Agent": "POKETIMES-RSS-Sync/1.0",
}

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    )
})


# ----------------------------------------
# 공통 유틸리티
# ----------------------------------------

def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat()


def normalize_url(url):
    if not url:
        return ""

    from urllib.parse import urlunparse

    parsed = urlparse(url.strip())

    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path.rstrip("/"),
        "",
        parsed.query,
        ""
    ))


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return default


def save_sync_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    temp_file = SYNC_FILE.with_suffix(".tmp")

    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(
            state,
            file,
            ensure_ascii=False,
            indent=2
        )

    temp_file.replace(SYNC_FILE)


def load_site_items():
    result = {}

    for site_id in ("pokemon-go", "pokemon-news"):
        path = STATE_DIR / f"{site_id}.json"
        data = load_json(path, {})
        items = data.get("items", [])

        if isinstance(items, list):
            result[site_id] = items
        else:
            result[site_id] = []

    return result


# ----------------------------------------
# Notion API
# ----------------------------------------

def notion_request(method, endpoint, payload=None):
    url = f"{API_BASE}{endpoint}"

    for attempt in range(4):
        response = requests.request(
            method,
            url,
            headers=HEADERS,
            json=payload,
            timeout=30
        )

        if response.status_code == 429:
            retry_after = int(
                response.headers.get("Retry-After", "2")
            )
            print(f"[Notion 대기] {retry_after}초")
            time.sleep(retry_after)
            continue

        if response.status_code >= 500 and attempt < 3:
            time.sleep(2 ** attempt)
            continue

        if not response.ok:
            print("[Notion API 오류]", response.status_code)
            print(response.text[:1500])
            response.raise_for_status()

        if response.text:
            return response.json()

        return {}

    raise RuntimeError("Notion API 요청 재시도 횟수를 초과했습니다.")


def get_data_source():
    return notion_request(
        "GET",
        f"/data_sources/{DATA_SOURCE_ID}"
    )


def find_property(properties, name, expected_type):
    prop = properties.get(name)

    if not prop:
        raise RuntimeError(
            f"Notion 속성 '{name}'을 찾을 수 없습니다."
        )

    actual_type = prop.get("type")

    if actual_type != expected_type:
        raise RuntimeError(
            f"'{name}' 속성 유형이 다릅니다. "
            f"필요: {expected_type}, 실제: {actual_type}"
        )

    return name


def validate_properties():
    data_source = get_data_source()
    properties = data_source.get("properties", {})

    title_name = None

    for name, prop in properties.items():
        if prop.get("type") == "title":
            title_name = name
            break

    if not title_name:
        raise RuntimeError(
            "Notion 데이터 소스에서 제목(Title) 속성을 찾지 못했습니다."
        )

    find_property(
        properties,
        "이벤트 시작일",
        "date"
    )
    find_property(
        properties,
        "출처",
        "url"
    )

    print("[Notion 속성 확인 완료]")
    print("제목 속성:", title_name)
    print("이벤트 시작일 / 수집일 / 출처 확인 완료")

    return title_name


def notion_source_exists(source_url):
    payload = {
        "filter": {
            "property": "출처",
            "url": {
                "equals": source_url
            }
        },
        "page_size": 1
    }

    result = notion_request(
        "POST",
        f"/data_sources/{DATA_SOURCE_ID}/query",
        payload
    )

    return bool(result.get("results"))


def rich_text(text):
    text = str(text or "").strip()

    if not text:
        text = "-"

    return [{
        "type": "text",
        "text": {
            "content": text[:2000]
        }
    }]


# ----------------------------------------
# 기사 본문 추출
# ----------------------------------------

def meta_content(soup, *names):
    for name in names:
        tag = soup.find(
            "meta",
            attrs={"property": name}
        )

        if not tag:
            tag = soup.find(
                "meta",
                attrs={"name": name}
            )

        if tag and tag.get("content"):
            return tag["content"].strip()

    return ""


def extract_jsonld(soup):
    descriptions = []
    images = []

    for script in soup.find_all(
        "script",
        type="application/ld+json"
    ):
        try:
            data = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue

        objects = data if isinstance(data, list) else [data]

        for obj in objects:
            if not isinstance(obj, dict):
                continue

            description = obj.get("description")
            if isinstance(description, str):
                descriptions.append(description)

            image = obj.get("image")

            if isinstance(image, str):
                images.append(image)
            elif isinstance(image, dict):
                if image.get("url"):
                    images.append(image["url"])
            elif isinstance(image, list):
                for value in image:
                    if isinstance(value, str):
                        images.append(value)
                    elif isinstance(value, dict) and value.get("url"):
                        images.append(value["url"])

    return descriptions, images


def extract_article(url):
    result = {
        "description": "",
        "summary": "",
        "image": "",
        "event_date": "",
    }

    try:
        response = SESSION.get(url, timeout=25)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        description = meta_content(
            soup,
            "og:description",
            "description",
            "twitter:description"
        )

        image = meta_content(
            soup,
            "og:image",
            "twitter:image"
        )

        jsonld_descriptions, jsonld_images = extract_jsonld(soup)

        if not description and jsonld_descriptions:
            description = jsonld_descriptions[0]

        if not image and jsonld_images:
            image = jsonld_images[0]

        if image:
            image = urljoin(url, image)

        # 본문 후보 영역 정리
        for tag in soup.find_all([
            "script",
            "style",
            "noscript",
            "nav",
            "footer",
            "header",
            "aside",
            "form"
        ]):
            tag.decompose()

        main = (
            soup.find("article")
            or soup.find("main")
            or soup.body
            or soup
        )

        paragraphs = []

        for tag in main.find_all(["h1", "h2", "h3", "p", "li"]):
            text = tag.get_text(" ", strip=True)

            if len(text) < 15:
                continue

            if text not in paragraphs:
                paragraphs.append(text)

        full_text = " ".join(paragraphs)

        if not description:
            description = full_text[:500]

        summary = make_summary(
            description,
            paragraphs
        )

        result["description"] = description
        result["summary"] = summary
        result["image"] = image
        result["event_date"] = extract_event_date(
            full_text or description
        )

    except requests.RequestException as error:
        print("[기사 본문 수집 실패]", url, error)

    return result


# ----------------------------------------
# 간단한 문장 추출 요약
# ----------------------------------------

def make_summary(description, paragraphs):
    source = " ".join(
        [description] + paragraphs
    )

    source = re.sub(r"\s+", " ", source).strip()

    sentences = re.split(
        r"(?<=[.!?。])\s+|(?<=다\.)\s+",
        source
    )

    keywords = (
        "이벤트", "개최", "진행", "기간", "등장",
        "배포", "보상", "참가", "시작", "종료",
        "업데이트", "공개", "발매", "선물"
    )

    selected = []

    for sentence in sentences:
        sentence = sentence.strip()

        if len(sentence) < 15:
            continue

        if sentence in selected:
            continue

        if any(word in sentence for word in keywords):
            selected.append(sentence)

        if len(selected) >= 4:
            break

    if not selected:
        selected = [
            sentence.strip()
            for sentence in sentences
            if len(sentence.strip()) >= 15
        ][:3]

    summary = "\n".join(
        f"• {sentence[:450]}"
        for sentence in selected
    )

    return summary[:1800] or description[:1000] or "기사 내용을 확인해 주세요."


# ----------------------------------------
# 이벤트 시작일 추출
# ----------------------------------------

def extract_event_date(text):
    if not text:
        return ""

    # 날짜 표현과 이벤트 진행 표현이 가까운 문장만 검사
    sentences = re.split(r"[.!?\n]", text)

    patterns = [
        r"(20\d{2})[년./-]\s*(\d{1,2})[월./-]\s*(\d{1,2})일?",
        r"(\d{1,2})월\s*(\d{1,2})일",
        r"(20\d{2})-(\d{2})-(\d{2})",
    ]

    event_words = (
        "기간", "개최", "진행", "시작",
        "등장", "참가", "이벤트", "부터"
    )

    for sentence in sentences:
        if not any(word in sentence for word in event_words):
            continue

        for pattern in patterns:
            match = re.search(pattern, sentence)

            if not match:
                continue

            values = match.groups()

            try:
                if len(values) == 3:
                    year, month, day = map(int, values)
                else:
                    year = datetime.now().year
                    month, day = map(int, values)

                candidate = datetime(
                    year,
                    month,
                    day
                ).date()

                return candidate.isoformat()

            except ValueError:
                continue

    return ""


# ----------------------------------------
# Notion 페이지 생성
# ----------------------------------------

def make_blocks(item, article, is_test):
    blocks = []

    if is_test:
        blocks.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": rich_text(
                    "자동 수집 테스트 게시글"
                ),
                "icon": {
                    "type": "emoji",
                    "emoji": "🧪"
                }
            }
        })

    if article.get("image"):
        blocks.append({
            "object": "block",
            "type": "image",
            "image": {
                "type": "external",
                "external": {
                    "url": article["image"]
                }
            }
        })

    blocks.extend([
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": rich_text("핵심 내용")
            }
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": rich_text(
                    article.get("summary", "")
                )
            }
        }
    ])

    event_date = article.get("event_date")

    blocks.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": rich_text(
                f"이벤트 시작일: {event_date}"
                if event_date
                else "이벤트 시작일: 기사에서 확인되지 않음"
            )
        }
    })

    blocks.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{
                "type": "text",
                "text": {
                    "content": "원문 기사 보기",
                    "link": {
                        "url": item["url"]
                    }
                }
            }]
        }
    })

    return blocks


def create_notion_page(item, article, title_name, is_test):
    source_url = item["url"]

    if notion_source_exists(source_url):
        print("[중복 방지] Notion에 이미 존재:", source_url)
        return True

    properties = {
        title_name: {
            "title": rich_text(item.get("title", "제목 없음"))
        },
        "이벤트 시작일": {
            "date": (
                {"start": article["event_date"]}
                if article.get("event_date")
                else None
            )
        }
        "출처": {
            "url": source_url
        }
    }

    payload = {
        "parent": {
            "type": "data_source_id",
            "data_source_id": DATA_SOURCE_ID
        },
        "properties": properties,
        "children": make_blocks(
            item,
            article,
            is_test
        )
    }

    notion_request(
        "POST",
        "/pages",
        payload
    )

    print("[Notion 등록 완료]", item.get("title", ""))
    return True


# ----------------------------------------
# 최초 기준 설정 및 신규 글 동기화
# ----------------------------------------

def item_key(item):
    return normalize_url(item.get("url", ""))


def ordered_items(site_id, items):
    items = [
        item for item in items
        if item_key(item)
    ]

    if site_id == "pokemon-news":
        def timestamp(item):
            try:
                return int(item.get("date", 0))
            except (ValueError, TypeError):
                return 0

        items.sort(
            key=timestamp,
            reverse=True
        )

    # GO는 크롤러가 페이지에서 가져온 순서를 유지
    return items


def initialize_state(site_items):
    baseline = set()
    tests = []

    for site_id, items in site_items.items():
        items = ordered_items(site_id, items)

        if not items:
            print(f"[최초 기준] {site_id}: 기사 없음")
            continue

        latest = items[0]
        latest_key = item_key(latest)

        tests.append({
            "site_id": site_id,
            "item": latest
        })

        for item in items[1:]:
            baseline.add(item_key(item))

        print(
            f"[테스트 대상] {site_id}: "
            f"{latest.get('title', '')}"
        )

    state = {
        "initialized": True,
        "initialized_at": now_iso(),
        "baseline_urls": sorted(baseline),
        "synced_urls": [],
    }

    save_sync_state(state)

    return state, tests


def main():
    print("================================")
    print("Notion 자동 동기화 시작")
    print("================================")

    if not NOTION_TOKEN or not DATA_SOURCE_ID:
        raise RuntimeError(
            "NOTION_TOKEN 또는 NOTION_DATA_SOURCE_ID가 설정되지 않았습니다."
        )

    title_name = validate_properties()
    site_items = load_site_items()

    state = load_json(SYNC_FILE, {})
    first_run = not state.get("initialized", False)

    if first_run:
        print("[최초 실행] 사이트별 최신 글 1개씩 테스트합니다.")
        state, test_items = initialize_state(site_items)

        candidates = [
            (entry["site_id"], entry["item"], True)
            for entry in test_items
        ]

    else:
        baseline = set(state.get("baseline_urls", []))
        synced = set(state.get("synced_urls", []))

        candidates = []

        for site_id, items in site_items.items():
            for item in ordered_items(site_id, items):
                key = item_key(item)

                if not key or key in baseline or key in synced:
                    continue

                candidates.append(
                    (site_id, item, False)
                )

        print(
            f"[신규 후보] {len(candidates)}개"
        )

    success_count = 0
    failure_count = 0

    for site_id, item, is_test in candidates:
        url = item.get("url", "")
        key = item_key(item)

        print("\n--------------------------------")
        print("사이트:", site_id)
        print("제목:", item.get("title", ""))
        print("주소:", url)

        try:
            article = extract_article(url)

            create_notion_page(
                item,
                article,
                title_name,
                is_test
            )

            synced = set(state.get("synced_urls", []))
            synced.add(key)
            state["synced_urls"] = sorted(synced)

            save_sync_state(state)
            success_count += 1

            # Notion API 요청 간격 확보
            time.sleep(0.5)

        except Exception as error:
            print("[등록 실패]", url)
            print(error)
            failure_count += 1

    print("\n================================")
    print("Notion 동기화 종료")
    print("성공:", success_count)
    print("실패:", failure_count)
    print("================================")


if __name__ == "__main__":
    main()

