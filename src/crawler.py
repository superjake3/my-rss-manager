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

    soup = BeautifulSoup(response.text, "html.parser")

    # 진단 정보 출력
    print("페이지 제목:", soup.title.get_text(strip=True) if soup.title else "없음")

    print("=== JavaScript 파일 주소 ===")
    for script in soup.find_all("script", src=True):
        print(urljoin(site_url, script["src"]))

    print("=== HTML 내용 일부 ===")
    print(response.text[:1800])

    # 뉴스 수집
    items = []
    seen = set()

    links = soup.find_all("a", href=True)

    print(f"페이지에서 발견한 전체 링크: {len(links)}개")

    for link in links:
        raw_url = link.get("href", "").strip()

        if not raw_url:
            continue

        article_url = urljoin(site_url, raw_url)

        if not get_news_url_rule(site_id, article_url):
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

    print(f"[{site['name']}] 최종 수집: {len(items)}개")

    if len(items) == 0:
        print("뉴스를 찾지 못했습니다.")

    return items
