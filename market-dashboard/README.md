# GOLD & FX Market Dashboard

GitHub Pages의 `/market-dashboard/` 경로에서 제공하는 설치형 PWA입니다.

## 표시 지표
- 국제 금 현물: USD / troy ounce (XAUS)
- USD/KRW 참고 환율 (fxapi.app)
- 국제 금 가격 × 환율 ÷ 31.1034768 = KRW / gram 환산 기준가
- 금 1돈(3.75g) 환산
- KRX 금 99.99% 일별 종가와 국제 환산 기준가의 가격 차이
- KRX 금 가격의 7·30거래일 변동률, 최근 30거래일 그래프
- 국제 금 가격과 환율의 일간 변화를 비교하는 학습용 시장 노트

## 자동 수집
- GitHub Actions가 한국 시간 평일 16:10에 실행되도록 설정되어 있습니다.
- KRX 금시장 일별 종가를 수집하고, XAUS 국제 금 가격 및 fxapi.app 환율을 함께 기록합니다.
- 최근 365거래일 데이터를 `data/market-history.json`에 누적합니다.
- 저장소 Secrets에 `KRX_AUTH_KEY`를 등록해야 KRX 수집이 실행됩니다.
- KRX 데이터는 실시간 호가가 아닌 거래소 일별 종가입니다. 국제 금과 환율의 기록 시각도 다를 수 있습니다.

## 해석 주의
시장 노트는 국제 금 가격과 환율의 산술적 변화를 비교하는 학습용 설명입니다. 실제 시장 원인을 확정하거나 매수·매도 신호를 제공하지 않습니다. 국내 금 가격 차이는 KRX 종가와 국제 금 환산 기준가의 기준 시각 및 시장 구조 차이를 포함할 수 있습니다.

## 설치
GitHub Pages 배포 후 Android Chrome에서 사이트를 열고 브라우저 메뉴의 '홈 화면에 추가' 또는 설치 안내를 선택하세요. 이 방식은 홈 화면 아이콘으로 전체 화면 앱을 여는 PWA이며, 런처 화면에 숫자가 계속 표시되는 네이티브 위젯은 아닙니다.

## 데이터 제공처
- https://xaus.com/api/
- https://fxapi.app/
- https://openapi.krx.co.kr/
