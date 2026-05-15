# CS Story 작성 절차

CS(Customer Success) 관점 스토리는 **기존 Market Story를 재작성** 하여 수치를 최대한 제거하고 맥락·흐름 위주로 서술한다. 일반 Story가 투자 의사결정용이라면 CS Story 는 고객에게 시장 상황을 "이야기로" 전달하는 용도다.

**공통 규칙(존댓말·forward-looking·세션 시각·인과방향·요일·고점 검증·표기)은 `SKILL.md` 본문 참조.**

---

## 전제

- **선행 조건**: 해당 날짜의 일반 Story 가 이미 `_story.html` 에 존재
- **대상 탭**: `<div id="tab-cs">` / placeholder `<!-- CS_STORY_PLACEHOLDER -->`
- **별도 파일 저장**: `YYYY-MM-DD_cs.html` (generate.py 가 sibling 으로 자동 저장)
- **적용 범위**: 일간·주간·월간 모두 동일 패턴

## Step 1: 기존 Story 읽기

`output/summary/YYYY-MM/YYYY-MM-DD_story.html` 을 Read. 사실관계(이벤트·종목·정책·인과)는 그대로 유지한다. 시간순 인과·세션 간 forward-looking 금지 규칙은 일반 Story 와 동일하게 적용된다.

## Step 2: 수치 제거 규칙

**제거 대상**:
- 퍼센트 수치 (`+0.46%`, `-1.22%`)
- 가격·지수 숫자 (`1,224,000원`, `6,417.93`, `59,586`)
- 시가총액·거래량·OHLC 숫자
- 섹터별 · 종목별 퍼센트 나열 (`중공업 +4.05%, 산업재 +2.34%`)
- KPI 테이블·metric-item 블록 내부 숫자 (UI 블록 자체를 들어내고 서술로 대체)

**유지 가능** (맥락상 필수일 때만):
- 심리적 앵커가 되는 정수 이정표: "10거래일 연속", "5,000조 돌파", "사상 최고치" (숫자 없는 표현 OK)
- 날짜·요일
- 종목명·지수명·ETF 티커·이벤트명·정책 키워드·인명

**대체 표현 가이드**:
| 수치 중심 (원본) | 맥락 중심 (CS) |
|-----------------|---------------|
| 코스피 +0.46%(6,417.93)로 사상 최고치 | 코스피가 사상 최고가를 이틀째 경신 |
| SK하이닉스 +4.97%(1,224,000원) 급등 | SK하이닉스가 다시 강하게 반등하며 주도주 입지를 굳혔습니다 |
| 닛케이 +0.40%, 상하이 +0.52%, 항셍 -1.22% | 닛케이·상하이는 강세, 항셍은 약세로 아시아 내 차별화 |
| VIX 18.3 → 16.5 (-9.8%) | 변동성지수가 한 단계 내려앉으며 변동성 경보가 풀렸습니다 |

## Step 3: 표기 규칙 (Market Story 와 동일)

- 지수·종목·통화명은 한국어 단독: `코스피`, `나스닥`, `금`, `달러/원`, `WTI유`
- 영문 약어도 한국어로: `사상 최고가`, `연초 대비`, `주간 대비`, `월간 대비`, `장단기 스프레드`
- 색상 컨벤션: 상승=빨간(`hl-up`), 하락=파란(`hl-down`) — 한국 주식창 기준

## Step 4: 톤 조정

- **흐름-앵커로 문장 연결**: "전일 상승세를 이어받아 아시아 장에서 한국이 다시 앞장섰습니다"
- **비유·스토리텔링 허용**: "랠리가 반도체에서 전통 산업으로 바통을 넘기는 모습"
- **전문 용어는 짧은 풀이**: "브레드스(breadth, 상승 종목 수)", "레인지 상단(최근 고점 부근)"
- **의사결정 권유 금지**: "비중 확대 권장", "매수 타이밍" 같은 표현은 쓰지 않는다. 관찰·설명만.

## Step 5: HTML 주입

**HTML 골격 — cs-hero + cs-section 조합** (Market Story 의 `.story-hero` 와 시각적으로 구분되는 오렌지 계열, CSS 는 tab-cs 블록 안에 인라인 포함해 과거 보고서에도 포터블):

```html
<style>
  .cs-hero{background:linear-gradient(135deg,#fff5eb,#fde9d3);border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:12px;padding:28px 32px;margin-bottom:24px}
  .cs-hero h2{font-size:13px;color:var(--accent);letter-spacing:2px;text-transform:uppercase;margin-bottom:12px}
  .cs-hero .cs-subtitle{font-size:12px;color:var(--muted);margin-bottom:16px}
  .cs-text{font-size:16px;color:#2d3148;line-height:1.9}
  .cs-text p{margin-bottom:14px}
  .cs-text p:last-child{margin-bottom:0}
  .cs-section{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px 28px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}
  .cs-section h3{font-size:17px;font-weight:600;color:#1a1d2e;margin-bottom:10px}
  .cs-section p{font-size:15px;color:#2d3148;line-height:1.85;margin-bottom:10px}
  .cs-section p:last-child{margin-bottom:0}
  .cs-footer{font-size:12px;color:var(--muted);border-top:1px solid var(--border);padding-top:12px;margin-top:8px}
</style>

<div class="cs-hero">
  <h2>CS Story — 고객 설명용</h2>
  <div class="cs-subtitle">{date} ({요일}) · 수치 대신 맥락·흐름 중심</div>
  <div class="cs-text">
    <p>{아시아 세션 흐름 — 수치 없이}</p>
    <p>{유럽 세션 흐름}</p>
    <p>{미국 세션 흐름}</p>
  </div>
</div>

<div class="cs-section">
  <h3>{국기 + 주요 테마 1}</h3>
  <p>{맥락·배경·의미}</p>
</div>

<!-- 필요한 만큼 cs-section 블록 반복 -->

<div class="cs-section">
  <h3>📅 이번 주·이번 달 관점</h3>
  <p>{WTD/MTD 맥락 서술}</p>
  <p class="cs-footer">CS Story 는 Market Story 를 수치 대신 맥락·흐름 중심으로 재구성한 고객 설명용 버전입니다. 구체적 수치는 Market Story / Data Dashboard 탭을 참고하세요.</p>
</div>

```

**절대 쓰지 말 것**: `.story-section`, `.story-content` — Market Summary HTML 에 정의돼 있지 않은 클래스 (research 보고서의 CSS 이므로 여기선 무스타일 상태가 된다).

**주입 단계**:

1. **일간**: `output/summary/YYYY-MM/YYYY-MM-DD.html` Read → `<div id="tab-cs" class="tab-panel">` ~ `</div><!-- /tab-cs -->` 블록 Edit → 같은 내용으로 `YYYY-MM-DD_cs.html` Edit (동기화)
2. **주간/월간**: 같은 패턴 (`weekly/YYYY-WNN.html` + `_cs.html`, `monthly/YYYY-MM.html` + `_cs.html`).

placeholder (`<!-- CS_STORY_PLACEHOLDER -->`) 가 남아있는 HTML 이면 `generate.py` / `generate_periodic.py` 를 한 번 재실행해 탭 구조를 최신화한 뒤 주입한다. `_inject_existing_story()` 외부 직접 호출은 여전히 금지 — Story 탭 규칙과 동일.

## 주간 / 월간 CS Story 적용 가이드

기간이 늘어남에 따라 CS Story 의 구조와 톤을 조정한다.

**주간 (작성 시점: 해당 주 마지막 영업일, 보통 금요일)**
- **헤로 단락**: 5 영업일을 한 흐름으로 압축 — 월·화·수·목·금 각 하루를 한 문장씩 (수치 없이)
- **테마 섹션**: 그 주의 핵심 테마 3~5 개. 각 섹션은 cs-section 박스 + 한국기·미국기·매크로·원자재 등 카테고리 이모지로 구분
- **주차 위치 표기**: 헤로 부제에 "ISO 주차 W{NN} · 5/5 영업일 경과" 명시
- **마무리 카드**: 📅 이번 달 관점 (MTD 흐름을 자연어로)
- 본체 HTML(`weekly/YYYY-WNN.html`)·sibling(`_cs.html`) 동시 갱신

**월간 (작성 시점: 해당 월 마지막 영업일)**
- **헤로 단락**: 한 달 전체를 1~2 문단으로 — 월초/월중/월말 흐름 (수치 없이)
- **테마 섹션**: 그 달의 핵심 테마 5~7 개 (CS 이므로 짧고 평이하게). 주간 CS 보다 약간 더 길게.
- **월말 시점 표기**: 헤로 부제에 "YYYY년 M월 N 영업일 종합" 명시
- **마무리 카드**: 📅 다음 달·분기 관점 (전망은 OK, 사후 참조 X)
- 본체(`monthly/YYYY-MM.html`)·sibling(`_cs.html`) 동시 갱신

**공통 — 주간/월간 모두**
- 일간 CS 와 동일 CSS(cs-hero, cs-section, cs-footer) 재사용. 기간 단위만 헤로 부제로 명시.
- 수치 제거 규칙·톤 조정 규칙은 일간과 동일.
- "이 주에 일어난 일을 한 호흡으로 이어서" 라는 흐름-앵커 톤 유지.

## 자가 검증 체크리스트

- [ ] 기존 Story 원본의 사실관계(이벤트·인과·시간순)를 그대로 전달하는가?
- [ ] 퍼센트·가격·거래량·OHLC 숫자가 본문에서 사라졌는가? (의도적 심리 앵커는 예외)
- [ ] 종목명·지수명·날짜·요일·이벤트명은 유지되었는가?
- [ ] 세션 간 forward-looking 금지 규칙을 그대로 지켰는가? (원본에 있다면 그 부분이 잘못된 것 — 원본부터 수정)
- [ ] 톤이 "설명·관찰" 인가, "권유·전망" 인가? 후자면 다시 작성.
- [ ] `_cs.html` sibling 파일이 생성·갱신되었는가?
