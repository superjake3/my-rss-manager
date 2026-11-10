# GOLD & FX Market Dashboard

GitHub Pages의 `/market-dashboard/` 경로에서 제공하는 설치형 PWA입니다.

## 표시 지표
- 국제 금 현물: USD / troy ounce (XAUS)
- USD/KRW 참고 환율 (fxapi.app)
- 국제 금 가격 × 환율 ÷ 31.1034768 = KRW / gram 환산 기준가
- 금 1돈(3.75g) 환산
- 실제 국내 시세 수동 입력 및 환산 기준가 대비 차이

## 주의
KRW/g는 국내 KRX 금시장 또는 금은방 실거래가가 아니라 국제 금 가격과 환율로 계산한 참고용 환산값입니다. 국내 시세 비교는 사용자가 출처를 확인한 원/g 값을 상세 화면에 직접 입력해야 합니다. 차트는 앱이 실행된 동안 수집한 값만 저장하며, 과거 시세 데이터가 아닙니다.

## 설치
GitHub Pages 배포 후 Android Chrome에서 사이트를 열고 브라우저 메뉴의 '홈 화면에 추가' 또는 설치 안내를 선택하세요. 이 방식은 홈 화면 아이콘으로 전체 화면 앱을 여는 PWA이며, 런처 화면에 숫자가 계속 표시되는 네이티브 위젯은 아닙니다.

## 데이터 제공처
- https://xaus.com/api/
- https://fxapi.app/
