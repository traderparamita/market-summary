# Stocks Story 작성 가이드 (일간 `tab-stocks`)

`market_summary` 일간 보고서의 **Stocks 탭**은 두 부분으로 구성된다:
1. **Stocks Story** (Claude 작성, 3~5문단) — 그날 종목 단위의 이야기
2. **4섹션 표** (generate.py 자동 생성) — KR Top 20 + US Top 20 + Asia Top 20 + 기타

본 가이드는 **Stocks Story** 부분의 작성 규칙을 정의한다.

---

## When to Use

- 일간 보고서의 `tab-stocks` 안 `<!-- STOCKS_STORY_PLACEHOLDER -->` 영역을 채울 때
- `/market-full` 워크플로우의 Story 작성 Step에서 호출
- 사용자가 "오늘 stocks story 써줘" 같은 자연어로 요청할 때

---

## 핵심 원칙

### 1. 데이터 우선 (Data-first)

본문 작성 전 반드시 그날 종목 변동 데이터를 추출:

```bash
.venv/bin/python <<'PY'
import pandas as pd
TARGET = '2026-05-18'
PREV   = '2026-05-15'   # 직전 영업일

df = pd.read_csv('history/market_data.csv')
df['DATE'] = pd.to_datetime(df['DATE'])

piv = df[(df['CATEGORY']=='stocks') & (df['DATE'].isin([pd.Timestamp(PREV), pd.Timestamp(TARGET)]))].pivot_table(
    index='TICKER', columns='DATE', values='CLOSE', aggfunc='first'
)
piv.columns = ['prev','curr']
piv['pct'] = (piv['curr']/piv['prev']-1)*100
piv = piv.dropna()

xl = pd.read_excel('history/아시아종목.xlsx', sheet_name='전체')
name_to_country = dict(zip(xl['종목명'], xl['국가']))
piv['country'] = piv.index.map(lambda x: name_to_country.get(x, ''))

print('TOP 10:', piv.sort_values('pct', ascending=False).head(10).to_string())
print('BOTTOM 10:', piv.sort_values('pct').head(10).to_string())
PY
```

이 데이터를 기반으로 다음을 판단:
- 가장 큰 단일 종목 폭등/폭락 (단순 등락보다 **놀라움 정도** 기준)
- 그룹별 흐름 (KR/US/Asia/EV/반도체·SPE/은행 등 클러스터)
- 그날의 핵심 1~2 테마

### 2. 구조: Hero + 4~5 단락

```html
<div class="story-hero">
  <h2>오늘의 종목 이야기</h2>
  <div class="story-text">
    <p>[총괄 1단락 — 그날의 큰 그림 + 가장 강한 시그너처 종목 1~2]</p>
    <p><strong>🇯🇵 일본</strong>: [일본 종목 흐름 단락]</p>
    <p><strong>🇨🇳 중국</strong>: [중국 종목 흐름 단락 + 반도체 자립 vs EV 디스퍼션]</p>
    <p><strong>🇰🇷 한국 + 🇹🇼 대만</strong>: [한국·대만 종목 + ADR/외국시장 거래 시 컨텍스트]</p>
    <p>[선택] <strong>🇮🇳 인도 / 🇻🇳 베트남 / 🇭🇰 홍콩</strong>: [신흥 아시아 종목 흐름]</p>
  </div>
</div>
```

### 3. 본문 톤

- 존댓말 (~했습니다, ~됐습니다, ~입니다)
- 자세하지만 간결 (한 단락 100~250자)
- **종목명 표기**: 종목명 + 한글 보조 가능 (예: "Recruit", "Mizuho FG(미즈호 FG)", "삼성전자")
- **수치**: 종목당 1~2개 핵심 % (소수점 1자리, 보조는 정수)
- **인과**: '~로 인해', '~의 결과로' 같은 명시적 연결어 사용

### 4. CSS 화이트리스트 (tab-stocks 블록)

`tab-stocks`는 `tab-story`와 달리 hook 검증 대상이 아니지만, 일관성 위해 다음 클래스만 사용 권장:

- 구조: `story-hero`, `story-text`
- 강조: `hl-up` (빨강), `hl-down` (파랑), `hl-warn` (주황), `hl-accent` (오렌지)
- 인라인 `<strong>` 으로 종목명·국가 강조

---

## 작성 가이드 — 시점·인과·디스퍼션

### Time

- **D일 종가** vs **D-1 종가**의 % 변동만 사용
- D+1 거래 시간 데이터 사용 금지 (forward-looking)
- "다음 거래일 어떻게 될 것이다" 같은 forecast는 **Outlook 탭**의 역할이므로 Stocks Story 에서는 자제

### 인과 — '왜 움직였나'

다음 채널 중 1~2개를 본문에 명시:
1. **실적/가이던스** — 1Q 매출, 영업이익, EPS 가이던스 발표
2. **정책/지정학** — 미·중 관계, 정상회담, 수출 통제, 관세
3. **매크로 연결** — 환율, 금리, 유가, 매크로 지표 변화
4. **테마/모멘텀** — AI 인프라, 반도체 자립, EV, 방산, 메모리 사이클
5. **개별 이벤트** — M&A, 임상 데이터, 노조, 경영진 변동

검증 가능한 채널이 없다면 "~로 추정됩니다" / "~배경으로 해석됩니다" 정도의 신중한 추정 표현.

### 디스퍼션 — 같은 그룹 내 정반대 방향 짚기

W20 보고서의 핵심 패턴이었던 "**중국 반도체 자립주 +15~36% vs 일본 반도체 장비주 −10~14%**" 같은 디스퍼션이 그날 시장의 가장 의미 있는 시그널인 경우가 많다. 이런 디스퍼션이 보이면 본문에서 **반드시 1단락**으로 짚는다.

### 클러스터 예시

- **반도체 SPE** (Tokyo Electron, Disco, Lasertec, Advantest, SUMCO, NAURA, AMEC, Hwatsing)
- **HBM·메모리 모듈** (SK하이닉스, Samsung, Micron, Longsys, Biwin Storage, Montage Tech, GigaDevice)
- **광통신 인프라** (Zhongji Innolight, Yangtze Optical, Eoptolink)
- **빅테크** (Tencent, Alibaba, Meituan, Baidu, NetEase)
- **EV·배터리** (BYD, CATL, Li Auto, XPeng, Tesla, Hyundai Motor, Kia)
- **메가뱅크** (Mizuho FG, KB Financial, ICICI, HDFC, BOA, JPM)
- **방산** (Hanwha Aerospace, IHI, Lockheed)
- **콩글로머릿** (Reliance, Hitachi, Mitsubishi Corp, Mitsui, Samsung)

---

## 자동화 워크플로우 (`/market-full`)

`/market-full YYYY-MM-DD` 실행 시 자동으로 호출되는 Step:

1. Market Story 작성 (기존)
2. CS Story 작성 (기존)
3. PM Story 작성 (기존)
4. **Stocks Story 작성** (신규) ← 본 가이드
5. Macro & Events 작성 (기존)
6. Sources 탭 채움 (기존)

각 Step은 sibling 파일(`_story.html`, `_cs.html`, `_pm.html`, `_stocks.html`, `_macro.html`, `_sources.html`)에 저장되며 다음 generate.py 호출 시 자동으로 보존된다.

---

## 검증 체크리스트

작성 완료 후 다음 확인:

- [ ] 본문 길이 1500~3500자 (너무 짧지도 길지도 않게)
- [ ] 모든 종목명·% 가 `history/market_data.csv` 와 일치
- [ ] 단락별로 국가 또는 테마 명확 구분
- [ ] 인과 채널 명시 (실적·정책·매크로·테마·이벤트 중 하나)
- [ ] 존댓말 일관성
- [ ] forward-looking 표현 없음 (예: "내일 ~할 것이다" 금지)
- [ ] CSS 클래스는 화이트리스트 (story-hero, story-text, hl-*) 만 사용
- [ ] 4섹션 표(자동 생성)와 본문이 자연스럽게 연결 (표 위 한 줄 코멘트 가능)

---

## 예시 — W21 첫날(2026-05-18) 작성

[output/summary/2026-05/2026-05-18.html](../../../../output/summary/2026-05/2026-05-18.html) 의 Stocks 탭 참조. 다음 구조:

- 1 단락: 한국 휴장 + 일본·중국·베트남 강세 vs 한국·대만 약세 총괄
- 2 단락: 🇯🇵 일본 — Recruit +16.6% vs 매크로주 약세
- 3 단락: 🇨🇳 중국 — 반도체·메모리 강세 + Li Auto −14.2% 디스퍼션
- 4 단락: 🇻🇳 베트남 — collectors 확장 후 첫 시그널 (BaoViet +6.9%, Vietcombank +4.1%)
- 5 단락: 🇰🇷🇹🇼 한국·대만 — KOSPI 휴장 무관, ADR 큰 폭 약세

총 2433자, 본문 시간 정확성 검증 통과.
