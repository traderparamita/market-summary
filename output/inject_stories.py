#!/usr/bin/env python3
"""Inject Market Story HTML into all placeholder files for 2025-01 and 2025-02."""
import os

STORIES = {}

# ═══════════════════════════════════════════════════════════════
# JANUARY 2025
# ═══════════════════════════════════════════════════════════════

STORIES["2025-01-08"] = """<!-- ── Story ── -->
<div class="story-hero"><h2>오늘의 시장 이야기</h2><div class="story-text">
<strong>삼성전자 +3.43%, CES 효과로 한국 시장이 빛났습니다.</strong><br><br>
KOSPI가 <span class="hl-up">+1.16%</span>(2,521)로 상승했습니다. CES(세계 최대 가전전시회)에서 AI 관련 신기술이 쏟아지면서 삼성전자가 <span class="hl-up">+3.43%</span> 급등했고, 이것이 KOSPI 전체를 끌어올렸습니다.<br><br>
미국은 S&P500 <span class="hl-up">+0.16%</span>, NASDAQ <span class="hl-down">-0.06%</span>으로 보합세였습니다. 어제 NVIDIA 급락(-6%) 충격이 아직 남아있지만, 금리(4.69%)가 더 오르지 않으면서 시장이 안도했습니다. 천연가스는 한파 지속으로 <span class="hl-up">+5.86%</span> 또 올랐습니다.
</div></div>
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">오늘의 흐름</div><div style="font-size:12px;color:var(--muted);margin-bottom:16px;">화살표를 따라가 보세요.</div>
<div class="causal-chain">
  <div class="cause-node"><div class="node-label">촉매</div><div class="node-title">CES 2025 개막</div><div class="node-detail">AI, 반도체, 로봇 신기술 발표</div><div class="node-impact up">기대감</div></div>
  <div class="cause-arrow">&rarr;</div>
  <div class="cause-node"><div class="node-label">수혜</div><div class="node-title">삼성전자 +3.43%</div><div class="node-detail">AI 반도체 수요 기대</div><div class="node-impact up">KOSPI 견인</div></div>
  <div class="cause-arrow">&rarr;</div>
  <div class="cause-node"><div class="node-label">미국</div><div class="node-title">금리 안정화</div><div class="node-detail">4.69%에서 추가 상승 멈춤</div><div class="node-impact" style="color:var(--muted)">보합</div></div>
  <div class="cause-arrow">&rarr;</div>
  <div class="cause-node"><div class="node-label">에너지</div><div class="node-title">천연가스 +5.86%</div><div class="node-detail">미국 한파 지속</div><div class="node-impact hl-warn">급등</div></div>
</div>
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">세계 시장 릴레이</div><div style="font-size:12px;color:var(--muted);margin-bottom:16px;">아시아 &rarr; 유럽 &rarr; 미국</div>
<div class="session-grid">
  <div class="session-block asia"><div class="session-header"><div class="session-icon asia">&#127471;&#127477;</div><div><div class="session-name">아시아</div><div class="session-time">09:00~15:30</div></div></div><span class="session-verdict verdict-up">강세</span><ul class="session-events"><li>KOSPI <span class="hl-up">+1.16%</span> &mdash; 삼성전자 CES 효과</li><li>환율 1,452원(원화 강세 지속)</li></ul><div class="session-kpi"><div class="s-kpi"><div class="s-kpi-label">KOSPI</div><div class="s-kpi-value up">+1.16%</div></div><div class="s-kpi"><div class="s-kpi-label">닛케이</div><div class="s-kpi-value down">-0.26%</div></div></div></div>
  <div class="session-block europe"><div class="session-header"><div class="session-icon europe">&#127466;&#127482;</div><div><div class="session-name">유럽</div><div class="session-time">17:00~01:30</div></div></div><span class="session-verdict verdict-mixed">혼조</span><ul class="session-events"><li>유럽 시장은 미국 금리 우려와 CES 기대 사이에서 혼조</li></ul><div class="session-kpi"><div class="s-kpi"><div class="s-kpi-label">DAX</div><div class="s-kpi-value" style="color:var(--muted)">보합</div></div><div class="s-kpi"><div class="s-kpi-label">FTSE</div><div class="s-kpi-value" style="color:var(--muted)">보합</div></div></div></div>
  <div class="session-block us"><div class="session-header"><div class="session-icon us">&#127482;&#127480;</div><div><div class="session-name">미국</div><div class="session-time">23:30~06:00</div></div></div><span class="session-verdict verdict-mixed">보합</span><ul class="session-events"><li>S&P500 <span class="hl-up">+0.16%</span>, NASDAQ <span class="hl-down">-0.06%</span></li><li>TSMC <span class="hl-down">-2.03%</span> 약세 지속</li></ul><div class="session-kpi"><div class="s-kpi"><div class="s-kpi-label">S&P 500</div><div class="s-kpi-value up">+0.16%</div></div><div class="s-kpi"><div class="s-kpi-label">NASDAQ</div><div class="s-kpi-value down">-0.06%</div></div></div></div>
</div>
<div class="cross-asset"><h2>자산 간 연결 고리</h2><div class="sub">CES와 금리가 시장에 미치는 영향입니다.</div>
  <div class="af-map">
    <div class="af-node"><div class="af-node-title">CES 2025</div><div class="af-node-value">AI 신기술</div><div class="af-node-chg up">기대감</div></div><div class="af-arrow"><span class="arr">&rarr;</span><span class="lbl">반도체</span></div><div class="af-node"><div class="af-node-title">삼성전자</div><div class="af-node-value">상승</div><div class="af-node-chg up">+3.43%</div></div><div class="af-arrow"><span class="arr">&rarr;</span><span class="lbl">KOSPI</span></div><div class="af-node"><div class="af-node-title">KOSPI</div><div class="af-node-value">2,521</div><div class="af-node-chg up">+1.16%</div></div>
    <div class="af-node"><div class="af-node-title">미국 금리</div><div class="af-node-value">4.69%</div><div class="af-node-chg hl-warn">고수준</div></div><div class="af-arrow"><span class="arr">&rarr;</span><span class="lbl">원화 강세</span></div><div class="af-node"><div class="af-node-title">USD/KRW</div><div class="af-node-value">1,452원</div><div class="af-node-chg up">-0.52%</div></div><div class="af-arrow"><span class="arr">&rarr;</span><span class="lbl">에너지</span></div><div class="af-node"><div class="af-node-title">WTI</div><div class="af-node-value">$73.32</div><div class="af-node-chg down">-1.25%</div></div>
  </div></div>
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">알아두면 좋은 시장 상식</div><div style="font-size:12px;color:var(--muted);margin-bottom:16px;">오늘의 핵심 개념들입니다.</div>
<div class="insight-grid">
  <div class="insight-card"><span class="badge" style="background:rgba(59,110,230,0.1);color:var(--accent)">CES</span><h3>CES가 주가에 미치는 영향</h3><p>CES에서 혁신적 기술이 발표되면 관련 기업 주가가 올라갑니다. 올해는 AI 에이전트, 자율주행, 로봇이 핵심 주제입니다. 삼성전자 AI 가전 발표가 +3.43% 상승의 원동력이었습니다.</p><div class="metric-row"><div class="metric-item"><div class="metric-label">삼성전자</div><div class="metric-value up">+3.43%</div></div><div class="metric-item"><div class="metric-label">KOSPI</div><div class="metric-value up">+1.16%</div></div></div></div>
  <div class="insight-card"><span class="badge" style="background:rgba(212,139,7,0.1);color:var(--warn)">보합</span><h3>보합세란?</h3><p><strong>보합세</strong>란 주가가 거의 변하지 않는 상태입니다. S&P500 +0.16%처럼 큰 뉴스를 앞두고 투자자들이 관망할 때 나타납니다. 금요일 고용보고서를 앞두고 신중한 모습입니다.</p><div class="metric-row"><div class="metric-item"><div class="metric-label">S&P500</div><div class="metric-value">+0.16%</div></div></div></div>
  <div class="insight-card"><span class="badge" style="background:rgba(211,84,0,0.1);color:var(--oil)">에너지</span><h3>천연가스의 롤러코스터</h3><p>이번 주 천연가스: -8% &rarr; +9% &rarr; +5%. 기상 예보 한 줄에 10%씩 움직이는 극도로 변동성 큰 상품입니다. 일반 투자자에게는 위험이 매우 큽니다.</p><div class="metric-row"><div class="metric-item"><div class="metric-label">천연가스</div><div class="metric-value up">+5.86%</div></div></div></div>
  <div class="insight-card"><span class="badge" style="background:rgba(13,155,106,0.1);color:var(--up)">환율</span><h3>원화 강세 지속</h3><p>원/달러 환율이 1,474원(1/2) &rarr; 1,452원(오늘)으로 계속 내려가고 있습니다. 외국인 투자자들이 한국 주식을 다시 사기 시작한 신호일 수 있습니다.</p><div class="metric-row"><div class="metric-item"><div class="metric-label">USD/KRW</div><div class="metric-value up">1,452원</div></div></div></div>
</div>
<div class="risk-section"><h2>앞으로 주의해야 할 점</h2><ul class="risk-items">
  <li class="risk-item"><span class="risk-tag high">높음</span><span><strong>금요일 고용보고서</strong><br>이번 주 최대 이벤트. 고용이 너무 강하면 금리 인하 기대 후퇴로 주가 하락 가능.</span></li>
  <li class="risk-item"><span class="risk-tag high">높음</span><span><strong>국채금리 4.69%</strong><br>4.7% 돌파 시 기술주 추가 매도 압력 가능.</span></li>
  <li class="risk-item"><span class="risk-tag med">보통</span><span><strong>트럼프 취임 D-12</strong><br>관세 정책 불확실성이 점점 커지고 있습니다.</span></li>
  <li class="risk-item"><span class="risk-tag med">보통</span><span><strong>삼성전자 실적 시즌 임박</strong><br>CES 효과가 실적으로 이어질지 확인 필요.</span></li>
</ul></div>"""

STORIES["2025-01-09"] = """<!-- ── Story ── -->
<div class="story-hero"><h2>오늘의 시장 이야기</h2><div class="story-text">
<strong>미국 시장 쉬는 날, 아시아는 자체적으로 움직였습니다.</strong><br><br>
오늘은 지미 카터 전 대통령 국장(국가장례)으로 미국 주식시장이 쉬었습니다. S&P500과 NASDAQ 모두 변동이 없습니다.
하지만 아시아 시장은 자체적으로 움직였습니다. KOSPI는 <span class="hl-up">+0.03%</span>로 거의 변동 없이 마감했고,
일본 닛케이는 <span class="hl-down">-0.94%</span> 하락했습니다.<br><br>
눈에 띄는 것은 삼성전자가 <span class="hl-down">-2.09%</span> 하락한 것입니다. 어제 CES 기대감으로 +3.43% 올랐지만, 오늘은 차익실현 매물이 나왔습니다.
금값은 <span class="hl-up">+0.72%</span>($2,684) 올라 안전자산 선호가 이어졌습니다.
</div></div>
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">오늘의 흐름</div><div style="font-size:12px;color:var(--muted);margin-bottom:16px;">화살표를 따라가 보세요.</div>
<div class="causal-chain">
  <div class="cause-node"><div class="node-label">배경</div><div class="node-title">미국 시장 휴장</div><div class="node-detail">카터 전 대통령 국장으로 뉴욕 증시 휴무</div><div class="node-impact" style="color:var(--muted)">거래 없음</div></div>
  <div class="cause-arrow">&rarr;</div>
  <div class="cause-node"><div class="node-label">아시아</div><div class="node-title">독자 움직임</div><div class="node-detail">미국 방향성 없이 아시아 자체 수급으로</div><div class="node-impact" style="color:var(--muted)">보합</div></div>
  <div class="cause-arrow">&rarr;</div>
  <div class="cause-node"><div class="node-label">삼성전자</div><div class="node-title">차익실현</div><div class="node-detail">어제 +3.43% 급등 후 이익 확정 매물</div><div class="node-impact hl-down">-2.09%</div></div>
  <div class="cause-arrow">&rarr;</div>
  <div class="cause-node"><div class="node-label">안전자산</div><div class="node-title">금값 상승</div><div class="node-detail">내일 고용보고서 앞두고 안전자산 선호</div><div class="node-impact up">+0.72%</div></div>
</div>
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">세계 시장 릴레이</div><div style="font-size:12px;color:var(--muted);margin-bottom:16px;">오늘은 미국 휴장으로 아시아/유럽만 거래되었습니다.</div>
<div class="session-grid">
  <div class="session-block asia"><div class="session-header"><div class="session-icon asia">&#127471;&#127477;</div><div><div class="session-name">아시아</div><div class="session-time">09:00~15:30</div></div></div><span class="session-verdict verdict-mixed">보합</span><ul class="session-events"><li>KOSPI <span class="hl-up">+0.03%</span>(2,522) 거의 변동 없음</li><li>삼성전자 <span class="hl-down">-2.09%</span> 차익실현</li><li>닛케이 <span class="hl-down">-0.94%</span></li></ul><div class="session-kpi"><div class="s-kpi"><div class="s-kpi-label">KOSPI</div><div class="s-kpi-value flat">+0.03%</div></div><div class="s-kpi"><div class="s-kpi-label">닛케이</div><div class="s-kpi-value down">-0.94%</div></div></div></div>
  <div class="session-block europe"><div class="session-header"><div class="session-icon europe">&#127466;&#127482;</div><div><div class="session-name">유럽</div><div class="session-time">17:00~01:30</div></div></div><span class="session-verdict verdict-mixed">약보합</span><ul class="session-events"><li>미국 휴장으로 유럽도 조용한 거래</li><li>영국 파운드화(GBP) <span class="hl-down">-0.95%</span> 약세</li></ul><div class="session-kpi"><div class="s-kpi"><div class="s-kpi-label">DAX</div><div class="s-kpi-value" style="color:var(--muted)">보합</div></div><div class="s-kpi"><div class="s-kpi-label">FTSE</div><div class="s-kpi-value" style="color:var(--muted)">보합</div></div></div></div>
  <div class="session-block us"><div class="session-header"><div class="session-icon us">&#127482;&#127480;</div><div><div class="session-name">미국</div><div class="session-time">휴장</div></div></div><span class="session-verdict verdict-mixed">휴장</span><ul class="session-events"><li>지미 카터 전 대통령 국장으로 뉴욕 증시 전체 휴무</li><li>내일 고용보고서 발표 예정 &mdash; 시장 긴장 고조</li></ul><div class="session-kpi"><div class="s-kpi"><div class="s-kpi-label">S&P 500</div><div class="s-kpi-value flat">휴장</div></div><div class="s-kpi"><div class="s-kpi-label">NASDAQ</div><div class="s-kpi-value flat">휴장</div></div></div></div>
</div>
<div class="cross-asset"><h2>자산 간 연결 고리</h2><div class="sub">미국 휴장일의 시장 움직임입니다.</div>
  <div class="af-map">
    <div class="af-node"><div class="af-node-title">미국 휴장</div><div class="af-node-value">카터 국장</div><div class="af-node-chg" style="color:var(--muted)">거래 없음</div></div><div class="af-arrow"><span class="arr">&rarr;</span><span class="lbl">방향성 부재</span></div><div class="af-node"><div class="af-node-title">아시아 보합</div><div class="af-node-value">자체 수급</div><div class="af-node-chg" style="color:var(--muted)">관망</div></div><div class="af-arrow"><span class="arr">&rarr;</span><span class="lbl">불확실성</span></div><div class="af-node"><div class="af-node-title">Gold</div><div class="af-node-value">$2,684</div><div class="af-node-chg up">+0.72%</div></div>
    <div class="af-node"><div class="af-node-title">삼성전자</div><div class="af-node-value">차익실현</div><div class="af-node-chg down">-2.09%</div></div><div class="af-arrow"><span class="arr">&rarr;</span><span class="lbl">단기 조정</span></div><div class="af-node"><div class="af-node-title">원/달러</div><div class="af-node-value">1,458원</div><div class="af-node-chg hl-warn">+0.42%</div></div><div class="af-arrow"><span class="arr">&rarr;</span><span class="lbl">에너지</span></div><div class="af-node"><div class="af-node-title">WTI</div><div class="af-node-value">$73.92</div><div class="af-node-chg up">+0.82%</div></div>
  </div></div>
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">알아두면 좋은 시장 상식</div><div style="font-size:12px;color:var(--muted);margin-bottom:16px;">오늘의 핵심 개념들입니다.</div>
<div class="insight-grid">
  <div class="insight-card"><span class="badge" style="background:rgba(59,110,230,0.1);color:var(--accent)">휴장</span><h3>미국 시장은 왜 쉬었을까?</h3><p>미국은 전직 대통령 서거 시 국장(National Day of Mourning)을 선포하고 증시를 하루 쉽니다. 오늘이 바로 그날입니다. 미국 시장이 쉬면 글로벌 투자자들도 큰 거래를 꺼려 전 세계 거래량이 줄어듭니다.</p><div class="metric-row"><div class="metric-item"><div class="metric-label">S&P500</div><div class="metric-value">휴장</div></div><div class="metric-item"><div class="metric-label">NASDAQ</div><div class="metric-value">휴장</div></div></div></div>
  <div class="insight-card"><span class="badge" style="background:rgba(217,48,79,0.1);color:var(--down)">차익실현</span><h3>차익실현이란?</h3><p><strong>차익실현</strong>이란 주가가 올라서 이익이 생겼을 때 주식을 팔아 이익을 확정하는 것입니다. 삼성전자가 어제 +3.43% 올랐는데, 오늘 -2.09% 빠진 것은 "어제 산 사람들이 오늘 팔아서 이익을 챙긴 것"입니다.</p><div class="metric-row"><div class="metric-item"><div class="metric-label">어제</div><div class="metric-value up">+3.43%</div></div><div class="metric-item"><div class="metric-label">오늘</div><div class="metric-value down">-2.09%</div></div></div></div>
  <div class="insight-card"><span class="badge" style="background:rgba(184,134,11,0.1);color:var(--gold)">금</span><h3>금값은 왜 오를까?</h3><p>내일 미국 고용보고서 발표를 앞두고 불확실성이 커지면, 투자자들은 안전한 자산으로 돈을 옮깁니다. 금(Gold)은 대표적인 안전자산으로, 불안할 때 가격이 오르는 경향이 있습니다.</p><div class="metric-row"><div class="metric-item"><div class="metric-label">Gold</div><div class="metric-value up">$2,684</div></div><div class="metric-item"><div class="metric-label">변동</div><div class="metric-value up">+0.72%</div></div></div></div>
  <div class="insight-card"><span class="badge" style="background:rgba(212,139,7,0.1);color:var(--warn)">고용</span><h3>내일 고용보고서가 왜 중요할까?</h3><p><strong>비농업 고용보고서(NFP)</strong>는 매달 첫째 금요일 발표되는 미국 고용 지표입니다. 일자리가 많이 늘면 경제가 좋다는 뜻이지만, 너무 강하면 "연준이 금리를 안 내리겠다" &rarr; 주가 하락으로 이어질 수 있습니다.</p><div class="metric-row"><div class="metric-item"><div class="metric-label">발표</div><div class="metric-value hl-warn">내일(1/10)</div></div></div></div>
</div>
<div class="risk-section"><h2>앞으로 주의해야 할 점</h2><ul class="risk-items">
  <li class="risk-item"><span class="risk-tag high">높음</span><span><strong>내일 고용보고서 발표</strong><br>이번 주 최대 이벤트. 결과에 따라 금리 방향이 결정되고, 주식시장이 크게 움직일 수 있습니다.</span></li>
  <li class="risk-item"><span class="risk-tag high">높음</span><span><strong>국채금리 4.69% 고공행진</strong><br>고용이 강하게 나오면 4.8%까지 오를 수 있습니다.</span></li>
  <li class="risk-item"><span class="risk-tag med">보통</span><span><strong>트럼프 취임 D-11</strong><br>관세 정책 구체화 가능성.</span></li>
  <li class="risk-item"><span class="risk-tag med">보통</span><span><strong>삼성전자 차익실현</strong><br>CES 이후 단기 조정이 어디까지 갈지 지켜봐야 합니다.</span></li>
</ul></div>"""

STORIES["2025-01-10"] = """<!-- ── Story ── -->
<div class="story-hero"><h2>오늘의 시장 이야기</h2><div class="story-text">
<strong>미국 고용 폭발! 25.6만 명 신규 고용에 시장이 흔들렸습니다.</strong><br><br>
오늘 발표된 미국 12월 비농업 고용이 <span class="hl-warn">25.6만 명</span> 증가로, 시장 예상(15.5만)을 크게 웃돌았습니다.
"경제가 너무 좋으면 연준(Fed)이 금리를 안 내린다" &rarr; S&P500 <span class="hl-down">-1.54%</span>, NASDAQ <span class="hl-down">-1.63%</span> 급락.
국채금리는 <span class="hl-warn">4.78%</span>까지 치솟았고, NVIDIA <span class="hl-down">-3.00%</span>, Apple <span class="hl-down">-2.41%</span> 등 대형 기술주가 일제히 하락했습니다.<br><br>
반면 원유는 <span class="hl-up">+3.58%</span>($76.57) 급등했습니다. 러시아에 대한 추가 제재 소식이 겹치면서 에너지 가격이 뛰었습니다. 한국 KOSPI는 <span class="hl-down">-0.24%</span>로 상대적으로 선방했습니다.
</div></div>
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">오늘의 흐름</div><div style="font-size:12px;color:var(--muted);margin-bottom:16px;">화살표를 따라가 보세요.</div>
<div class="causal-chain">
  <div class="cause-node"><div class="node-label">원인</div><div class="node-title">고용 25.6만 명</div><div class="node-detail">예상(15.5만) 크게 상회</div><div class="node-impact hl-warn">금리 인하 기대 후퇴</div></div>
  <div class="cause-arrow">&rarr;</div>
  <div class="cause-node"><div class="node-label">반응</div><div class="node-title">국채금리 4.78%</div><div class="node-detail">금리 급등, 달러 강세</div><div class="node-impact hl-warn">+1.77%</div></div>
  <div class="cause-arrow">&rarr;</div>
  <div class="cause-node"><div class="node-label">결과</div><div class="node-title">기술주 급락</div><div class="node-detail">NVIDIA -3%, Apple -2.4%</div><div class="node-impact hl-down">S&P500 -1.54%</div></div>
  <div class="cause-arrow">&rarr;</div>
  <div class="cause-node"><div class="node-label">에너지</div><div class="node-title">원유 +3.58%</div><div class="node-detail">러시아 추가 제재 소식</div><div class="node-impact hl-warn">$76.57</div></div>
</div>
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">세계 시장 릴레이</div><div style="font-size:12px;color:var(--muted);margin-bottom:16px;">아시아 &rarr; 유럽 &rarr; 미국</div>
<div class="session-grid">
  <div class="session-block asia"><div class="session-header"><div class="session-icon asia">&#127471;&#127477;</div><div><div class="session-name">아시아</div><div class="session-time">09:00~15:30</div></div></div><span class="session-verdict verdict-down">약세</span><ul class="session-events"><li>KOSPI <span class="hl-down">-0.24%</span>(2,516) &mdash; 고용 발표 전 관망세</li><li>닛케이 <span class="hl-down">-1.05%</span></li></ul><div class="session-kpi"><div class="s-kpi"><div class="s-kpi-label">KOSPI</div><div class="s-kpi-value down">-0.24%</div></div><div class="s-kpi"><div class="s-kpi-label">닛케이</div><div class="s-kpi-value down">-1.05%</div></div></div></div>
  <div class="session-block europe"><div class="session-header"><div class="session-icon europe">&#127466;&#127482;</div><div><div class="session-name">유럽</div><div class="session-time">17:00~01:30</div></div></div><span class="session-verdict verdict-down">하락</span><ul class="session-events"><li>고용 서프라이즈 직후 유럽 선물 하락</li><li>유가 강세가 유럽 에너지 비용 우려 자극</li></ul><div class="session-kpi"><div class="s-kpi"><div class="s-kpi-label">DAX</div><div class="s-kpi-value down">하락</div></div><div class="s-kpi"><div class="s-kpi-label">FTSE</div><div class="s-kpi-value down">하락</div></div></div></div>
  <div class="session-block us"><div class="session-header"><div class="session-icon us">&#127482;&#127480;</div><div><div class="session-name">미국</div><div class="session-time">23:30~06:00</div></div></div><span class="session-verdict verdict-down">급락</span><ul class="session-events"><li>S&P500 <span class="hl-down">-1.54%</span>, NASDAQ <span class="hl-down">-1.63%</span></li><li>NVIDIA <span class="hl-down">-3.00%</span>, Apple <span class="hl-down">-2.41%</span></li><li>천연가스 <span class="hl-up">+7.78%</span> 폭등 (한파+수요)</li></ul><div class="session-kpi"><div class="s-kpi"><div class="s-kpi-label">S&P 500</div><div class="s-kpi-value down">-1.54%</div></div><div class="s-kpi"><div class="s-kpi-label">NASDAQ</div><div class="s-kpi-value down">-1.63%</div></div></div></div>
</div>
<div class="cross-asset"><h2>자산 간 연결 고리</h2><div class="sub">강한 고용이 시장 전체에 미치는 영향입니다.</div>
  <div class="af-map">
    <div class="af-node"><div class="af-node-title">고용 25.6만</div><div class="af-node-value">예상 크게 상회</div><div class="af-node-chg hl-warn">서프라이즈</div></div><div class="af-arrow"><span class="arr">&rarr;</span><span class="lbl">금리 인하 후퇴</span></div><div class="af-node"><div class="af-node-title">10년 국채금리</div><div class="af-node-value">4.78%</div><div class="af-node-chg hl-warn">+1.77%</div></div><div class="af-arrow"><span class="arr">&rarr;</span><span class="lbl">기술주 압박</span></div><div class="af-node"><div class="af-node-title">NASDAQ</div><div class="af-node-value">19,162</div><div class="af-node-chg down">-1.63%</div></div>
    <div class="af-node"><div class="af-node-title">러시아 제재</div><div class="af-node-value">추가 제재</div><div class="af-node-chg hl-warn">공급 우려</div></div><div class="af-arrow"><span class="arr">&rarr;</span><span class="lbl">유가 급등</span></div><div class="af-node"><div class="af-node-title">WTI</div><div class="af-node-value">$76.57</div><div class="af-node-chg hl-warn">+3.58%</div></div><div class="af-arrow"><span class="arr">&rarr;</span><span class="lbl">물가 우려</span></div><div class="af-node"><div class="af-node-title">Gold</div><div class="af-node-value">$2,709</div><div class="af-node-chg up">+0.92%</div></div>
  </div></div>
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">알아두면 좋은 시장 상식</div><div style="font-size:12px;color:var(--muted);margin-bottom:16px;">오늘의 핵심 개념들입니다.</div>
<div class="insight-grid">
  <div class="insight-card"><span class="badge" style="background:rgba(212,139,7,0.1);color:var(--warn)">고용</span><h3>고용이 좋은데 왜 주가가 떨어져요?</h3><p><strong>"좋은 뉴스가 나쁜 뉴스"</strong>가 되는 순간입니다. 고용이 좋으면 경제가 건강하다는 뜻이지만, 너무 좋으면 연준이 "인플레이션(물가 상승)이 다시 올 수 있다" &rarr; "금리를 안 내리겠다"고 판단합니다. 높은 금리는 기업 비용을 높이고 주가를 누릅니다.</p><div class="metric-row"><div class="metric-item"><div class="metric-label">신규고용</div><div class="metric-value hl-warn">25.6만</div></div><div class="metric-item"><div class="metric-label">예상</div><div class="metric-value">15.5만</div></div></div></div>
  <div class="insight-card"><span class="badge" style="background:rgba(59,110,230,0.1);color:var(--accent)">금리</span><h3>국채금리 4.78%의 의미</h3><p>10년 국채금리가 4.78%면 2023년 10월 이후 최고 수준에 근접합니다. 당시 5%를 찍었을 때 주식시장이 큰 충격을 받았습니다. 지금도 5%에 가까워질수록 시장 압력이 커집니다.</p><div class="metric-row"><div class="metric-item"><div class="metric-label">10년금리</div><div class="metric-value hl-warn">4.78%</div></div><div class="metric-item"><div class="metric-label">VIX</div><div class="metric-value hl-warn">19.5</div></div></div></div>
  <div class="insight-card"><span class="badge" style="background:rgba(211,84,0,0.1);color:var(--oil)">원유</span><h3>러시아 제재와 유가</h3><p>미국이 러시아 석유에 대한 추가 제재를 발표하면서 원유 가격이 급등했습니다. 러시아는 세계 3대 산유국으로, 러시아산 원유 공급이 줄면 국제 유가가 오르고, 이는 전 세계 물가 상승으로 이어집니다.</p><div class="metric-row"><div class="metric-item"><div class="metric-label">WTI</div><div class="metric-value hl-warn">$76.57</div></div><div class="metric-item"><div class="metric-label">변동</div><div class="metric-value hl-warn">+3.58%</div></div></div></div>
  <div class="insight-card"><span class="badge" style="background:rgba(13,155,106,0.1);color:var(--up)">VIX</span><h3>VIX 19.5 &mdash; 경계 수준 진입</h3><p>VIX(공포지수)가 19.5로 올라 20에 근접했습니다. 20을 넘으면 "시장이 불안하다"는 신호입니다. 고용 서프라이즈와 금리 급등으로 투자자들의 불안감이 커지고 있습니다.</p><div class="metric-row"><div class="metric-item"><div class="metric-label">VIX</div><div class="metric-value hl-warn">19.5</div></div><div class="metric-item"><div class="metric-label">경계선</div><div class="metric-value">20</div></div></div></div>
</div>
<div class="risk-section"><h2>앞으로 주의해야 할 점</h2><ul class="risk-items">
  <li class="risk-item"><span class="risk-tag high">높음</span><span><strong>금리 인하 기대 급격히 후퇴</strong><br>시장은 이제 2025년 금리 인하를 1~2회로 축소 전망. 금리가 오래 높게 유지되면 주식, 부동산 모두 부담.</span></li>
  <li class="risk-item"><span class="risk-tag high">높음</span><span><strong>다음 주 CPI(물가지수) 발표</strong><br>1/15 소비자물가지수 발표. 물가도 높게 나오면 금리 인하가 더 늦어질 수 있습니다.</span></li>
  <li class="risk-item"><span class="risk-tag med">보통</span><span><strong>유가 급등 &rarr; 물가 압력</strong><br>WTI $76.57은 최근 몇 주 최고치. 유가가 $80을 넘으면 물가 상승 우려가 본격화됩니다.</span></li>
  <li class="risk-item"><span class="risk-tag med">보통</span><span><strong>트럼프 취임 D-10</strong><br>관세 + 높은 금리가 동시에 오면 시장 충격이 배가될 수 있습니다.</span></li>
</ul></div>"""

# Continue with remaining January dates...

STORIES["2025-01-13"] = """<!-- ── Story ── -->
<div class="story-hero"><h2>오늘의 시장 이야기</h2><div class="story-text">
<strong>유가 $79 돌파! 에너지 가격 급등이 시장을 압박했습니다.</strong><br><br>
WTI 원유가 <span class="hl-warn">+2.94%</span>($78.82)로 급등하며 올해 최고치를 경신했습니다. 러시아 추가 제재 여파가 계속되고 있습니다. KOSPI는 <span class="hl-down">-1.04%</span>(2,490)로 하락했고, 삼성전자도 <span class="hl-down">-2.17%</span> 빠졌습니다. 미국은 S&P500 <span class="hl-up">+0.16%</span>로 소폭 상승했지만, TSMC <span class="hl-down">-3.36%</span>, 반도체주는 여전히 약세입니다.<br><br>
트럼프 취임(1/20)이 일주일 앞으로 다가오면서 관세 정책 불확실성도 시장을 짓누르고 있습니다. 금값은 <span class="hl-down">-1.29%</span>로 차익실현 매물이 나왔습니다.
</div></div>
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">오늘의 흐름</div><div style="font-size:12px;color:var(--muted);margin-bottom:16px;">화살표를 따라가 보세요.</div>
<div class="causal-chain">
  <div class="cause-node"><div class="node-label">원인</div><div class="node-title">러시아 제재 강화</div><div class="node-detail">원유 공급 감소 우려</div><div class="node-impact hl-warn">유가 급등</div></div>
  <div class="cause-arrow">&rarr;</div>
  <div class="cause-node"><div class="node-label">결과</div><div class="node-title">WTI $78.82</div><div class="node-detail">+2.94% 올해 최고치</div><div class="node-impact hl-warn">물가 압력</div></div>
  <div class="cause-arrow">&rarr;</div>
  <div class="cause-node"><div class="node-label">영향</div><div class="node-title">한국 시장 약세</div><div class="node-detail">KOSPI -1.04%, 삼성 -2.17%</div><div class="node-impact hl-down">에너지 비용 우려</div></div>
  <div class="cause-arrow">&rarr;</div>
  <div class="cause-node"><div class="node-label">불확실성</div><div class="node-title">취임 D-7</div><div class="node-detail">트럼프 관세 정책 임박</div><div class="node-impact hl-warn">긴장 고조</div></div>
</div>
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">세계 시장 릴레이</div><div style="font-size:12px;color:var(--muted);margin-bottom:16px;">아시아 &rarr; 유럽 &rarr; 미국</div>
<div class="session-grid">
  <div class="session-block asia"><div class="session-header"><div class="session-icon asia">&#127471;&#127477;</div><div><div class="session-name">아시아</div><div class="session-time">09:00~15:30</div></div></div><span class="session-verdict verdict-down">하락</span><ul class="session-events"><li>KOSPI <span class="hl-down">-1.04%</span> &mdash; 유가 급등 + 관세 불안</li><li>삼성전자 <span class="hl-down">-2.17%</span></li></ul><div class="session-kpi"><div class="s-kpi"><div class="s-kpi-label">KOSPI</div><div class="s-kpi-value down">-1.04%</div></div><div class="s-kpi"><div class="s-kpi-label">닛케이</div><div class="s-kpi-value flat">0.00%</div></div></div></div>
  <div class="session-block europe"><div class="session-header"><div class="session-icon europe">&#127466;&#127482;</div><div><div class="session-name">유럽</div><div class="session-time">17:00~01:30</div></div></div><span class="session-verdict verdict-mixed">혼조</span><ul class="session-events"><li>유럽은 에너지 비용 상승에 민감한 지역</li><li>유가 상승이 인플레이션 우려 자극</li></ul><div class="session-kpi"><div class="s-kpi"><div class="s-kpi-label">DAX</div><div class="s-kpi-value" style="color:var(--muted)">혼조</div></div><div class="s-kpi"><div class="s-kpi-label">FTSE</div><div class="s-kpi-value" style="color:var(--muted)">혼조</div></div></div></div>
  <div class="session-block us"><div class="session-header"><div class="session-icon us">&#127482;&#127480;</div><div><div class="session-name">미국</div><div class="session-time">23:30~06:00</div></div></div><span class="session-verdict verdict-mixed">보합</span><ul class="session-events"><li>S&P500 <span class="hl-up">+0.16%</span>, NASDAQ <span class="hl-down">-0.38%</span></li><li>TSMC <span class="hl-down">-3.36%</span>, 반도체주 약세 지속</li><li>Tesla <span class="hl-up">+2.17%</span> 반등</li></ul><div class="session-kpi"><div class="s-kpi"><div class="s-kpi-label">S&P 500</div><div class="s-kpi-value up">+0.16%</div></div><div class="s-kpi"><div class="s-kpi-label">NASDAQ</div><div class="s-kpi-value down">-0.38%</div></div></div></div>
</div>
<div class="cross-asset"><h2>자산 간 연결 고리</h2><div class="sub">유가 급등이 모든 시장에 영향을 미치고 있습니다.</div>
  <div class="af-map">
    <div class="af-node"><div class="af-node-title">러시아 제재</div><div class="af-node-value">공급 감소</div><div class="af-node-chg hl-warn">지정학 리스크</div></div><div class="af-arrow"><span class="arr">&rarr;</span><span class="lbl">유가 상승</span></div><div class="af-node"><div class="af-node-title">WTI</div><div class="af-node-value">$78.82</div><div class="af-node-chg hl-warn">+2.94%</div></div><div class="af-arrow"><span class="arr">&rarr;</span><span class="lbl">물가 우려</span></div><div class="af-node"><div class="af-node-title">국채금리</div><div class="af-node-value">4.80%</div><div class="af-node-chg hl-warn">+0.57%</div></div>
    <div class="af-node"><div class="af-node-title">트럼프 취임</div><div class="af-node-value">D-7</div><div class="af-node-chg hl-warn">관세 우려</div></div><div class="af-arrow"><span class="arr">&rarr;</span><span class="lbl">달러 강세</span></div><div class="af-node"><div class="af-node-title">USD/KRW</div><div class="af-node-value">1,472원</div><div class="af-node-chg hl-warn">+1.17%</div></div><div class="af-arrow"><span class="arr">&rarr;</span><span class="lbl">수출 부담</span></div><div class="af-node"><div class="af-node-title">KOSPI</div><div class="af-node-value">2,490</div><div class="af-node-chg down">-1.04%</div></div>
  </div></div>
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">알아두면 좋은 시장 상식</div><div style="font-size:12px;color:var(--muted);margin-bottom:16px;">오늘의 핵심 개념들입니다.</div>
<div class="insight-grid">
  <div class="insight-card"><span class="badge" style="background:rgba(211,84,0,0.1);color:var(--oil)">원유</span><h3>러시아 제재가 유가에 미치는 영향</h3><p>러시아는 세계 3대 산유국입니다. 미국과 EU가 러시아산 원유에 제재를 가하면, 글로벌 원유 공급이 줄어들어 가격이 오릅니다. 유가가 오르면 한국은 석유를 수입에 의존하기 때문에 물가 부담이 커집니다.</p><div class="metric-row"><div class="metric-item"><div class="metric-label">WTI</div><div class="metric-value hl-warn">$78.82</div></div><div class="metric-item"><div class="metric-label">Brent</div><div class="metric-value hl-warn">+1.57%</div></div></div></div>
  <div class="insight-card"><span class="badge" style="background:rgba(59,110,230,0.1);color:var(--accent)">금리</span><h3>국채금리 4.80% 돌파</h3><p>10년 국채금리가 4.80%로 올해 최고입니다. 이 수준은 2023년 10월 "금리 공포"때와 가까워지고 있어 시장이 긴장하고 있습니다. 5%에 접근하면 주식시장 전반에 큰 압력이 됩니다.</p><div class="metric-row"><div class="metric-item"><div class="metric-label">10년금리</div><div class="metric-value hl-warn">4.80%</div></div></div></div>
  <div class="insight-card"><span class="badge" style="background:rgba(212,139,7,0.1);color:var(--warn)">관세</span><h3>취임 일주일 전, 긴장 고조</h3><p>트럼프 대통령이 1/20 취임하면 즉시 행정명령으로 관세를 부과할 수 있습니다. 중국산 제품 60%, 범용 관세 10~20%가 예고되어 있습니다. 이미 시장은 선제적으로 반응하기 시작했습니다.</p><div class="metric-row"><div class="metric-item"><div class="metric-label">취임일</div><div class="metric-value hl-warn">D-7</div></div></div></div>
  <div class="insight-card"><span class="badge" style="background:rgba(217,48,79,0.1);color:var(--down)">KOSPI</span><h3>한국 시장 왜 약해졌나?</h3><p>KOSPI가 -1.04% 하락하고 환율이 1,472원으로 다시 올랐습니다. 유가 급등(에너지 수입 비용 증가) + 관세 불안(수출 타격) + 정치 불확실성이 삼중으로 작용하고 있습니다.</p><div class="metric-row"><div class="metric-item"><div class="metric-label">KOSPI</div><div class="metric-value down">-1.04%</div></div><div class="metric-item"><div class="metric-label">삼성전자</div><div class="metric-value down">-2.17%</div></div></div></div>
</div>
<div class="risk-section"><h2>앞으로 주의해야 할 점</h2><ul class="risk-items">
  <li class="risk-item"><span class="risk-tag high">높음</span><span><strong>트럼프 취임(1/20) D-7</strong><br>취임 즉시 관세 행정명령 서명 가능. 중국, 멕시코, 캐나다가 주요 대상.</span></li>
  <li class="risk-item"><span class="risk-tag high">높음</span><span><strong>CPI 물가지수(1/15)</strong><br>수요일 발표. 물가도 예상보다 높으면 금리 인하가 사실상 불가능해질 수 있습니다.</span></li>
  <li class="risk-item"><span class="risk-tag med">보통</span><span><strong>유가 $80 접근</strong><br>WTI가 $80을 넘으면 인플레이션 재점화 우려가 본격화됩니다.</span></li>
  <li class="risk-item"><span class="risk-tag med">보통</span><span><strong>실적시즌 시작</strong><br>다음 주부터 미국 주요 은행들의 4분기 실적 발표가 시작됩니다.</span></li>
</ul></div>"""

# For remaining dates, I'll create a function to generate similar story HTML
def make_story(hero_text, causal_nodes, sessions, cross_nodes, insights, risks):
    """Helper to build story HTML from components."""
    # Build causal chain
    causal_html = ""
    for i, (label, title, detail, impact_class, impact_text) in enumerate(causal_nodes):
        if i > 0:
            causal_html += '  <div class="cause-arrow">&rarr;</div>\n'
        causal_html += f'  <div class="cause-node"><div class="node-label">{label}</div><div class="node-title">{title}</div><div class="node-detail">{detail}</div><div class="node-impact {impact_class}">{impact_text}</div></div>\n'

    # Build sessions
    session_html = ""
    for region, icon, name, time, verdict_class, verdict_text, events, kpis in sessions:
        events_html = "".join(f"<li>{e}</li>" for e in events)
        kpis_html = "".join(f'<div class="s-kpi"><div class="s-kpi-label">{k}</div><div class="s-kpi-value {c}">{v}</div></div>' for k, v, c in kpis)
        session_html += f'  <div class="session-block {region}"><div class="session-header"><div class="session-icon {region}">{icon}</div><div><div class="session-name">{name}</div><div class="session-time">{time}</div></div></div><span class="session-verdict {verdict_class}">{verdict_text}</span><ul class="session-events">{events_html}</ul><div class="session-kpi">{kpis_html}</div></div>\n'

    # Build cross-asset
    cross_html = ""
    for nodes in cross_nodes:
        for j, item in enumerate(nodes):
            if len(item) == 4:  # node
                title, value, chg, chg_class = item
                cross_html += f'<div class="af-node"><div class="af-node-title">{title}</div><div class="af-node-value">{value}</div><div class="af-node-chg {chg_class}">{chg}</div></div>'
            elif len(item) == 2:  # arrow
                arrow, label = item
                cross_html += f'<div class="af-arrow"><span class="arr">&rarr;</span><span class="lbl">{label}</span></div>'

    # Build insights
    insight_html = ""
    for badge_bg, badge_color, badge_text, title, body, metrics in insights:
        metrics_html = "".join(f'<div class="metric-item"><div class="metric-label">{l}</div><div class="metric-value {c}">{v}</div></div>' for l, v, c in metrics)
        insight_html += f'  <div class="insight-card"><span class="badge" style="background:{badge_bg};color:{badge_color}">{badge_text}</span><h3>{title}</h3><p>{body}</p><div class="metric-row">{metrics_html}</div></div>\n'

    # Build risks
    risk_html = ""
    for level, title, desc in risks:
        risk_html += f'    <li class="risk-item"><span class="risk-tag {level}">{("높음" if level == "high" else "보통")}</span><span><strong>{title}</strong><br>{desc}</span></li>\n'

    return f"""<!-- ── Story ── -->
<div class="story-hero"><h2>오늘의 시장 이야기</h2><div class="story-text">{hero_text}</div></div>
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">오늘의 흐름</div><div style="font-size:12px;color:var(--muted);margin-bottom:16px;">화살표를 따라가 보세요.</div>
<div class="causal-chain">
{causal_html}</div>
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">세계 시장 릴레이</div><div style="font-size:12px;color:var(--muted);margin-bottom:16px;">아시아 &rarr; 유럽 &rarr; 미국</div>
<div class="session-grid">
{session_html}</div>
<div class="cross-asset"><h2>자산 간 연결 고리</h2><div class="sub">시장의 자산들은 서로 연결되어 있습니다.</div>
  <div class="af-map">{cross_html}</div></div>
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">알아두면 좋은 시장 상식</div><div style="font-size:12px;color:var(--muted);margin-bottom:16px;">오늘의 핵심 개념들입니다.</div>
<div class="insight-grid">
{insight_html}</div>
<div class="risk-section"><h2>앞으로 주의해야 할 점</h2><ul class="risk-items">
{risk_html}</ul></div>"""

# Generate remaining stories using the helper function

STORIES["2025-01-14"] = make_story(
    '<strong>중국 상하이 +2.54%! 아시아에서 중국이 반등했습니다.</strong><br><br>KOSPI <span class="hl-up">+0.31%</span>(2,497), S&P500 <span class="hl-up">+0.11%</span>로 소폭 상승했습니다. 중국 상하이 지수가 <span class="hl-up">+2.54%</span>, 홍콩 항셍이 <span class="hl-up">+1.83%</span>로 강세를 보이며 아시아 전체를 끌어올렸습니다. 중국 정부의 경기 부양 기대감이 작용했습니다.<br><br>반면 일본 닛케이는 <span class="hl-down">-1.83%</span>로 약세. META <span class="hl-down">-2.31%</span>, Tesla <span class="hl-down">-1.72%</span>로 미국 기술주는 여전히 부진합니다. 이번 주 수요일 CPI(물가지수) 발표를 앞두고 시장이 조심스러운 모습입니다.',
    [("촉매", "중국 부양 기대", "정부 경기 부양책 기대감", "up", "상하이 +2.54%"),
     ("영향", "아시아 동반 상승", "홍콩 +1.83%, KOSPI +0.31%", "up", "아시아 강세"),
     ("한편", "미국 보합", "CPI 발표(수요일) 대기 모드", "flat", "S&P +0.11%"),
     ("우려", "기술주 약세", "META -2.31%, 금리 부담 지속", "hl-down", "나스닥 부진")],
    [("asia", "&#127471;&#127477;", "아시아", "09:00~15:30", "verdict-up", "강세",
      ['중국 상하이 <span class="hl-up">+2.54%</span>, 홍콩 <span class="hl-up">+1.83%</span>', 'KOSPI <span class="hl-up">+0.31%</span>, 닛케이 <span class="hl-down">-1.83%</span>'],
      [("KOSPI", "+0.31%", "up"), ("닛케이", "-1.83%", "down")]),
     ("europe", "&#127466;&#127482;", "유럽", "17:00~01:30", "verdict-mixed", "혼조",
      ['CPI 발표 대기로 유럽도 관망세'],
      [("DAX", "보합", ""), ("FTSE", "보합", "")]),
     ("us", "&#127482;&#127480;", "미국", "23:30~06:00", "verdict-mixed", "보합",
      ['S&P500 <span class="hl-up">+0.11%</span>', 'META <span class="hl-down">-2.31%</span>, Tesla <span class="hl-down">-1.72%</span>'],
      [("S&P 500", "+0.11%", "up"), ("NASDAQ", "-0.23%", "down")])],
    [[[("중국 부양 기대", "정책 발표", "경기 부양", "up"), ("&rarr;", "아시아 상승")],
      [("상하이", "3,200", "+2.54%", "up"), ("&rarr;", "심리 개선")],
      [("KOSPI", "2,497", "+0.31%", "up")]]],
    [("rgba(217,48,79,0.1)", "var(--down)", "CPI", "CPI(소비자물가지수)란?",
      '<strong>CPI</strong>는 우리가 일상에서 사는 물건들(식료품, 의류, 교통비 등)의 가격 변화를 측정한 숫자입니다. CPI가 오르면 "물가가 올랐다(인플레이션)"를 의미합니다. 수요일 발표되는 12월 CPI가 예상보다 높으면 금리 인하가 더 늦어질 수 있습니다.',
      [("CPI 발표", "1/15(수)", "hl-warn")]),
     ("rgba(13,155,106,0.1)", "var(--up)", "중국", "중국 경기 부양의 의미",
      '중국 정부가 경기를 살리기 위해 돈을 풀거나 세금을 줄이면, 중국에 물건을 많이 파는 한국 기업(삼성, 현대차 등)에도 좋은 소식입니다. 오늘 한국 시장이 오른 것도 이 기대감 덕분입니다.',
      [("상하이", "+2.54%", "up"), ("HSI", "+1.83%", "up")]),
     ("rgba(59,110,230,0.1)", "var(--accent)", "금리", "국채금리 소폭 하락",
      '금리가 4.79%로 소폭 내렸습니다(-0.31%). 금리가 조금이라도 내리면 주식시장에는 숨통이 트입니다. 하지만 CPI 결과에 따라 다시 오를 수 있습니다.',
      [("10년금리", "4.79%", ""), ("변동", "-0.31%", "up")]),
     ("rgba(212,139,7,0.1)", "var(--warn)", "실적", "실적시즌 시작",
      '이번 주부터 JP모건, 씨티그룹 등 미국 대형 은행들이 4분기 실적을 발표합니다. 은행 실적이 좋으면 경제가 건강하다는 신호, 나쁘면 경기 둔화 우려로 이어집니다.',
      [("JP모건", "1/15", "hl-accent"), ("씨티그룹", "1/15", "hl-accent")])],
    [("high", "수요일 CPI 발표", "12월 소비자물가지수 결과가 금리 인하 전망을 좌우합니다."),
     ("high", "트럼프 취임 D-6", "관세 정책 즉시 시행 가능성 점점 높아지고 있습니다."),
     ("med", "미국 은행 실적 발표", "JP모건 등 대형은행 실적이 경제 건전성의 바로미터입니다."),
     ("med", "유가 $79 고공행진", "에너지 가격이 높게 유지되면 물가 상승 압력이 커집니다.")])

STORIES["2025-01-15"] = make_story(
    '<strong>CPI 안도감! 물가 둔화에 시장이 화답했습니다.</strong><br><br>12월 미국 소비자물가지수(CPI)가 예상보다 양호하게 나왔습니다. 핵심 CPI(변동성 큰 식품/에너지 제외)가 전월 대비 +0.2%로 예상(+0.3%)보다 낮았습니다. "물가가 잡히고 있다!" &rarr; 연준 금리 인하 기대 회복 &rarr; S&P500 <span class="hl-up">+1.83%</span>, NASDAQ <span class="hl-up">+2.45%</span> 급등!<br><br>Tesla <span class="hl-up">+8.04%</span> 폭등, META <span class="hl-up">+3.85%</span>, Silver(은) <span class="hl-up">+3.94%</span>. 국채금리는 <span class="hl-up">4.65%</span>로 급락하며 시장에 안도감을 줬습니다. KOSPI는 <span class="hl-down">-0.02%</span>로 미국 CPI 발표 전 관망세였습니다.',
    [("촉매", "CPI 양호", "핵심 CPI +0.2% (예상 +0.3%)", "up", "물가 둔화"),
     ("반응", "금리 하락", "10년 국채금리 4.65%로 급락", "up", "금리 인하 기대"),
     ("결과", "기술주 폭등", "Tesla +8%, NASDAQ +2.45%", "up", "위험선호 회복"),
     ("한편", "유가 강세", "WTI $80 (+3.28%)", "hl-warn", "에너지 상승")],
    [("asia", "&#127471;&#127477;", "아시아", "09:00~15:30", "verdict-mixed", "관망",
      ['KOSPI <span class="hl-down">-0.02%</span> CPI 발표 대기', '상하이 <span class="hl-down">-0.43%</span>'],
      [("KOSPI", "-0.02%", "flat"), ("닛케이", "-0.08%", "flat")]),
     ("europe", "&#127466;&#127482;", "유럽", "17:00~01:30", "verdict-up", "상승",
      ['CPI 호재에 유럽도 반등'],
      [("DAX", "상승", "up"), ("FTSE", "상승", "up")]),
     ("us", "&#127482;&#127480;", "미국", "23:30~06:00", "verdict-up", "급등",
      ['S&P500 <span class="hl-up">+1.83%</span>, NASDAQ <span class="hl-up">+2.45%</span>', 'Tesla <span class="hl-up">+8.04%</span> 폭등!', '금리 4.65%로 급락'],
      [("S&P 500", "+1.83%", "up"), ("NASDAQ", "+2.45%", "up")])],
    [[[("CPI 양호", "물가 둔화", "금리 인하 기대", "up"), ("&rarr;", "금리 하락")],
      [("10년 국채금리", "4.65%", "-2.82%", "up"), ("&rarr;", "기술주 상승")],
      [("NASDAQ", "19,511", "+2.45%", "up")]]],
    [("rgba(13,155,106,0.1)", "var(--up)", "CPI", "CPI 결과가 왜 좋은 소식인가?",
      '핵심 CPI가 +0.2%로 나온 것은 물가 상승 속도가 둔화되고 있다는 뜻입니다. 연준이 올해 금리를 인하할 수 있다는 기대가 살아나면서 주식시장이 크게 올랐습니다.',
      [("핵심CPI", "+0.2%", "up"), ("예상", "+0.3%", "")]),
     ("rgba(217,48,79,0.1)", "var(--down)", "Tesla", "Tesla +8% 폭등",
      'Tesla가 하루 만에 +8% 올랐습니다. 금리 인하 기대가 살아나면 미래 성장에 베팅하는 주식이 가장 많이 오릅니다. Tesla는 대표적인 성장주여서 반응이 가장 컸습니다.',
      [("Tesla", "+8.04%", "up")]),
     ("rgba(211,84,0,0.1)", "var(--oil)", "원유", "WTI $80 돌파",
      '원유가 $80을 넘었습니다. CPI가 양호했지만 유가가 계속 오르면 물가가 다시 오를 수 있어 주의가 필요합니다.',
      [("WTI", "$80.04", "hl-warn"), ("변동", "+3.28%", "hl-warn")]),
     ("rgba(59,110,230,0.1)", "var(--accent)", "실적", "은행 실적 발표",
      'JP모건, 씨티그룹 등 대형 은행들이 호실적을 발표했습니다. 은행이 잘 벌었다는 것은 경제가 건강하다는 신호입니다.',
      [("JP모건", "호실적", "up"), ("씨티그룹", "호실적", "up")])],
    [("high", "트럼프 취임 D-5", "월요일 취임. 관세 행정명령이 첫날 나올 수 있습니다."),
     ("high", "유가 $80 돌파", "에너지 가격 상승이 인플레이션을 다시 자극할 수 있습니다."),
     ("med", "CPI 안도감의 지속성", "한 달 데이터로 안심하기 이릅니다. 다음 달 CPI도 중요합니다."),
     ("med", "실적시즌 본격화", "다음 주 TSMC, Netflix 등 기술기업 실적이 시장 방향을 좌우할 것입니다.")])

# Generate remaining stories more concisely for dates 16-31 Jan and all Feb

for date, hero, causal, asia_v, asia_l, eur_v, eur_l, us_v, us_l, risk1, risk2, risk3, risk4 in [
    ("2025-01-16",
     '<strong>TSMC +3.86%! 반도체 호실적에 기대감이 살아났습니다.</strong><br><br>KOSPI <span class="hl-up">+1.23%</span>(2,527)로 상승. S&P500 <span class="hl-down">-0.21%</span>로 소폭 하락했지만 TSMC(세계 최대 반도체 위탁생산 기업)가 <span class="hl-up">+3.86%</span> 급등하며 반도체 업종에 활기를 불어넣었습니다. 금리는 4.61%로 안정세를 보이고, 원/달러 환율은 1,437원으로 <span class="hl-up">-1.59%</span> 급락(원화 강세)했습니다.<br><br>다만 Apple <span class="hl-down">-4.04%</span>, Tesla <span class="hl-down">-3.36%</span>로 일부 대형주는 약세. NVIDIA도 <span class="hl-down">-1.96%</span>. 금값은 $2,746으로 <span class="hl-up">+1.25%</span> 상승하며 사상 최고치에 접근하고 있습니다.',
     [("촉매", "TSMC 호실적 기대", "AI 반도체 수요 강세 확인", "up", "+3.86%"), ("반응", "한국 반도체 동반 상승", "KOSPI +1.23%", "up", "한국 강세"), ("한편", "미국 혼조", "Apple -4%, Tesla -3%", "hl-down", "종목별 차별화"), ("안전자산", "금값 상승", "$2,746 +1.25%", "up", "사상최고 접근")],
     "verdict-up", "강세", "verdict-mixed", "혼조", "verdict-mixed", "혼조",
     "트럼프 취임 D-4", "금요일 취임 직전. 관세 행정명령 초읽기.", "Apple -4% 급락", "중국 아이폰 판매 부진 우려 지속.", "유가 $79 수준 유지", "에너지 가격이 높게 유지되고 있습니다.", "금값 사상 최고 접근", "불확실성 속 안전자산 수요 증가."),
    ("2025-01-17",
     '<strong>S&P500 +1.00%! 주간 마무리는 상승으로.</strong><br><br>이번 주를 마감하는 금요일, S&P500 <span class="hl-up">+1.00%</span>(5,997), NASDAQ <span class="hl-up">+1.51%</span>(19,630)로 강세 마감했습니다. 금리가 4.61%로 안정되면서 기술주가 반등한 것입니다. Broadcom <span class="hl-up">+3.50%</span>, NVIDIA <span class="hl-up">+3.10%</span>.<br><br>월요일은 마틴 루터 킹 데이(미국 공휴일)로 뉴욕 증시가 쉽니다. 그리고 화요일(1/21)이 바로 트럼프 취임 다음 날입니다. KOSPI는 <span class="hl-down">-0.16%</span>로 소폭 하락. 주말 사이에 큰 뉴스가 나올 수 있어 조심스러운 모습입니다.',
     [("배경", "금리 안정화", "4.61%, CPI 안도감 지속", "up", "금리 하락"), ("반응", "기술주 반등", "NVIDIA +3.1%, Broadcom +3.5%", "up", "NASDAQ +1.51%"), ("결과", "주간 마무리 강세", "S&P500 +1.00%", "up", "한 주 상승 마감"), ("주의", "취임 D-3", "월요일 공휴일, 화요일 첫 거래", "hl-warn", "불확실성")],
     "verdict-down", "소폭 하락", "verdict-mixed", "혼조", "verdict-up", "강세",
     "트럼프 취임 D-3(1/20 월)", "월요일 취임식. 화요일부터 시장 반응 시작.", "관세 행정명령 예고", "취임 첫날 중국, 멕시코, 캐나다 관세 서명 가능.", "유가 하락세", "WTI $77.88 (-1.02%). 취임 전 불확실성 반영.", "VIX 16.0 안정", "시장은 아직 공포 수준은 아닙니다."),
    ("2025-01-20",
     '<strong>트럼프 취임일! 미국은 쉬고, 아시아는 관망.</strong><br><br>오늘은 마틴 루터 킹 데이 공휴일로 미국 증시가 휴장입니다. 동시에 트럼프 대통령이 공식 취임했습니다. 아시아 시장은 관망세 속 KOSPI <span class="hl-down">-0.14%</span>, 닛케이 <span class="hl-up">+1.17%</span>. 홍콩 항셍은 <span class="hl-up">+1.75%</span>로 강세.<br><br>취임 연설에서 트럼프는 "미국 우선"을 강조했고, 관세 행정명령 서명이 임박해 있습니다. 내일 미국 시장이 열리면 트럼프 취임에 대한 본격적인 반응이 나올 것입니다.',
     [("이벤트", "트럼프 취임", "제47대 미국 대통령 공식 취임", "hl-warn", "정책 불확실성"), ("미국", "증시 휴장", "마틴 루터 킹 데이 공휴일", "", "거래 없음"), ("아시아", "관망세", "KOSPI -0.14%, 닛케이 +1.17%", "", "방향 탐색"), ("기대", "내일 본격 반응", "화요일 미국 시장 개장 시 반응", "hl-warn", "변동성 예고")],
     "verdict-mixed", "관망", "verdict-mixed", "관망", "verdict-mixed", "휴장",
     "내일 미국 시장 첫 반응", "트럼프 취임 후 첫 거래일. 관세 행정명령에 따라 시장 크게 움직일 수 있음.", "관세 행정명령 서명 임박", "중국 60%, 멕시코/캐나다 25% 관세 예고.", "삼성전자 약세", "삼성전자 -0.56%. 관세 불확실성이 한국 수출에 부담.", "환율 1,457원", "원화가 다시 약세로 돌아설 수 있는 위험."),
    ("2025-01-21",
     '<strong>트럼프 취임 다음 날, 시장은 의외로 강세!</strong><br><br>시장의 예상과 달리, 트럼프 취임 후 첫 거래일 S&P500이 <span class="hl-up">+0.88%</span>(6,049), NASDAQ <span class="hl-up">+0.64%</span>로 상승했습니다. 트럼프가 예상보다 온건한 관세 접근(즉시 부과 대신 검토 지시)을 보이면서 시장이 안도한 것입니다.<br><br>AI 투자 기대감도 큰 역할을 했습니다. 트럼프가 5,000억 달러 규모의 AI 인프라 투자 프로젝트 "스타게이트(Stargate)"를 발표했습니다. KOSPI는 <span class="hl-down">-0.08%</span>로 보합. VIX 15.1로 공포감은 낮은 수준입니다.',
     [("이벤트", "취임 첫 거래일", "예상보다 온건한 관세 접근", "up", "안도 랠리"), ("촉매", "Stargate 프로젝트", "AI 인프라 5,000억$ 투자 발표", "up", "AI 기대감"), ("반응", "미국 시장 상승", "S&P500 +0.88%, NASDAQ +0.64%", "up", "위험선호 회복"), ("한국", "KOSPI 보합", "관세 불확실성 여전", "flat", "-0.08%")],
     "verdict-mixed", "보합", "verdict-up", "상승", "verdict-up", "강세",
     "관세 정책 구체화 대기", "즉시 부과 대신 검토 지시를 내렸지만, 향후 관세가 현실화될 가능성은 여전합니다.", "Stargate AI 프로젝트 실현 가능성", "5,000억$ 규모의 AI 투자가 실현되면 반도체 수요 폭증이 예상됩니다.", "미국 금리 4.57% 하락", "금리가 내려가면서 주식시장에 좋은 환경이 조성되고 있습니다.", "KOSPI 소외감", "미국이 오르는 동안 한국은 관세 불안으로 보합."),
    ("2025-01-22",
     '<strong>S&P500 사상 최고치 접근! AI 투자 열기가 뜨겁습니다.</strong><br><br>NASDAQ <span class="hl-up">+1.28%</span>(20,009), S&P500 <span class="hl-up">+0.61%</span>(6,086)로 연이틀 상승. NASDAQ이 20,000을 다시 돌파했습니다! Stargate AI 프로젝트 발표 이후 AI 관련주가 전반적으로 강세입니다. NVIDIA <span class="hl-up">+2.27%</span>.<br><br>KOSPI도 <span class="hl-up">+1.15%</span>(2,547)로 동반 상승. 원/달러 환율은 1,426원으로 <span class="hl-up">-0.68%</span> 하락(원화 강세). 금값 $2,755로 사상 최고치 기록! 전반적으로 "리스크 온(위험 자산 선호)" 분위기입니다.',
     [("배경", "Stargate AI 효과 지속", "AI 5,000억$ 투자 기대감", "up", "기술주 강세"), ("반응", "NASDAQ 20,000 돌파", "NVIDIA +2.27%, TSMC +3.40%", "up", "AI 랠리"), ("동조", "KOSPI +1.15%", "한국 반도체주 동반 상승", "up", "원화 강세"), ("안전자산", "금 사상 최고", "$2,755 역대 최고치", "up", "안전+위험 동시 상승")],
     "verdict-up", "강세", "verdict-up", "상승", "verdict-up", "강세",
     "관세 현실화 리스크", "안도 랠리가 이어지고 있지만, 관세가 실제로 부과되면 시장이 급반전할 수 있습니다.", "과열 우려", "시장이 너무 빨리 오르면 조정(하락)이 올 수 있습니다.", "다음 주 연준 회의", "1/28-29 FOMC 회의. 금리 동결이 예상되지만 발언이 중요합니다.", "금값 사상 최고", "금이 오르는 것은 불확실성이 여전히 크다는 의미이기도 합니다."),
    ("2025-01-23",
     '<strong>KOSPI -1.24% 하락, AI 기대감 속 한국은 소외.</strong><br><br>미국 시장은 S&P500 <span class="hl-up">+0.53%</span>(6,119), NASDAQ <span class="hl-up">+0.22%</span>로 3일 연속 상승 중이지만, KOSPI는 <span class="hl-down">-1.24%</span>(2,515)로 역행했습니다. 외국인 투자자들이 한국 주식을 매도하면서 원/달러 환율도 1,434원으로 <span class="hl-warn">+0.60%</span> 올랐습니다(원화 약세).<br><br>META <span class="hl-up">+2.08%</span>로 강세, 하지만 Silver <span class="hl-down">-1.81%</span>, KOSDAQ <span class="hl-down">-1.13%</span>로 소형주와 원자재는 약세. AI 열기가 미국에 집중되고 한국은 소외되는 모습입니다.',
     [("배경", "미국 AI 랠리 지속", "S&P500 3일 연속 상승", "up", "+0.53%"), ("한국", "KOSPI 소외", "외국인 매도, 관세 불안", "hl-down", "-1.24%"), ("환율", "원화 약세", "1,434원 &rarr; 외국인 자금 이탈", "hl-warn", "+0.60%"), ("한편", "금값 하락", "위험선호로 안전자산 수요 감소", "down", "-0.16%")],
     "verdict-down", "하락", "verdict-up", "상승", "verdict-up", "상승",
     "한국 시장 소외 지속", "미국 AI 랠리가 한국 시장으로 파급되지 못하고 있습니다.", "다음 주 연준 회의(1/28-29)", "금리 동결 예상이지만, 파월 의장 발언이 핵심.", "관세 구체화 리스크", "트럼프 관세가 현실화되면 한국 수출 기업에 직접 타격.", "테슬라/애플 실적 발표 임박", "다음 주 빅테크 실적이 시장 방향을 좌우할 것입니다."),
    ("2025-01-24",
     '<strong>VIX 14.9 &mdash; 시장은 차분하게 한 주를 마감했습니다.</strong><br><br>금요일, 시장은 큰 변동 없이 한 주를 마무리했습니다. S&P500 <span class="hl-down">-0.29%</span>, NASDAQ <span class="hl-down">-0.50%</span>로 소폭 하락. KOSPI <span class="hl-up">+0.85%</span>(2,537)는 어제의 급락에서 일부 만회했습니다.<br><br>NVIDIA <span class="hl-down">-3.12%</span>, Tesla <span class="hl-down">-1.41%</span>로 AI 대장주가 조정을 받았습니다. 다음 주에 연준(Fed) 회의와 빅테크(Apple, Microsoft, Meta, Tesla) 실적 발표가 예정되어 있어 투자자들이 관망하는 분위기입니다. VIX 14.9로 시장은 매우 안정적입니다.',
     [("배경", "주간 마무리", "큰 이벤트 없이 조용한 금요일", "", "관망세"), ("조정", "AI 대장주 하락", "NVIDIA -3.12%, Tesla -1.41%", "hl-down", "차익실현"), ("한국", "KOSPI 반등", "+0.85% 어제 급락에서 회복", "up", "2,537"), ("대기", "다음 주 이벤트", "FOMC + 빅테크 실적", "hl-warn", "긴장 대기")],
     "verdict-up", "반등", "verdict-mixed", "보합", "verdict-down", "소폭 하락",
     "다음 주 연준 회의(1/28-29)", "금리 동결이 예상되지만 파월 의장의 발언 톤이 중요합니다.", "빅테크 실적 발표", "Microsoft(1/29), Meta(1/29), Tesla(1/29), Apple(1/30) 실적이 줄줄이.", "NVIDIA 조정", "AI 대장주가 -3% 빠진 것은 과열 후 건전한 조정일 수 있습니다.", "관세 현실화 리스크", "트럼프 행정부가 관세 세부사항을 발표할 수 있습니다."),
    ("2025-01-27",
     '<strong>DeepSeek 충격! NVIDIA -16.97%로 AI 역사상 최대 급락.</strong><br><br>중국 AI 스타트업 <strong>DeepSeek</strong>이 미국 AI 기업들보다 훨씬 적은 비용으로 고성능 AI 모델을 만들었다는 소식이 전해지면서 시장이 폭풍에 빠졌습니다. NVIDIA <span class="hl-down">-16.97%</span>(역사상 단일 기업 하루 최대 시가총액 증발), Broadcom <span class="hl-down">-17.40%</span>, TSMC <span class="hl-down">-13.33%</span>.<br><br>NASDAQ <span class="hl-down">-3.07%</span>, S&P500 <span class="hl-down">-1.46%</span>. "AI에 비싼 칩이 필요 없을 수도 있다"는 공포가 반도체 생태계 전체를 뒤흔든 것입니다. 반면 Apple <span class="hl-up">+3.18%</span>, META <span class="hl-up">+1.91%</span>는 "저렴한 AI는 오히려 소프트웨어에 좋다"는 논리로 올랐습니다.',
     [("충격", "DeepSeek 등장", "저비용 고성능 AI 모델 공개", "hl-down", "AI 칩 수요 의문"), ("패닉", "반도체 폭락", "NVIDIA -17%, Broadcom -17%", "hl-down", "역사적 급락"), ("반면", "소프트웨어 강세", "Apple +3.2%, META +1.9%", "up", "저렴한 AI 수혜"), ("결과", "시장 충격", "NASDAQ -3.07%", "hl-down", "AI 버블 우려")],
     "verdict-mixed", "보합", "verdict-down", "하락", "verdict-down", "급락",
     "DeepSeek 충격의 지속 여부", "AI 반도체 수요가 실제로 줄어들지는 두고 봐야 합니다. 과도한 공포일 수 있습니다.", "NVIDIA 추가 하락 가능성", "역사적 급락 후 추가 매도가 이어질 수 있습니다.", "연준 회의(내일~모레)", "이번 충격과 별개로 금리 결정이 나옵니다.", "반도체 생태계 재평가", "삼성전자, SK하이닉스 등 한국 반도체 기업에도 영향 불가피."),
    ("2025-01-28",
     '<strong>DeepSeek 충격에서 반등! NVIDIA +8.93%.</strong><br><br>"어제 너무 과도하게 빠졌다"는 판단 속 강한 저가매수가 들어왔습니다. NVIDIA <span class="hl-up">+8.93%</span>, TSMC <span class="hl-up">+5.25%</span>, Apple <span class="hl-up">+3.65%</span>. NASDAQ <span class="hl-up">+2.03%</span>, S&P500 <span class="hl-up">+0.92%</span>로 시장이 빠르게 반등했습니다.<br><br>"DeepSeek이 무서운 건 맞지만, AI 수요 자체가 줄어드는 건 아니다"라는 냉정한 분석이 우세해졌습니다. KOSPI는 설 연휴로 보합. 연준 FOMC 회의 첫날이기도 합니다.',
     [("어제", "DeepSeek 패닉", "NVIDIA -17% 역사적 급락", "hl-down", "과매도"), ("오늘", "저가매수 유입", "너무 싸다는 판단", "up", "강한 반등"), ("반등", "기술주 회복", "NVIDIA +8.9%, TSMC +5.3%", "up", "NASDAQ +2.03%"), ("진행중", "FOMC 회의", "연준 금리 회의 첫날", "hl-warn", "내일 결과")],
     "verdict-mixed", "보합(설연휴)", "verdict-mixed", "혼조", "verdict-up", "강한 반등",
     "내일 FOMC 결과 발표", "금리 동결 예상이지만 파월 의장의 AI 관련 발언에 주목.", "DeepSeek 여파 지속 여부", "반등이 진짜인지, 일시적인지 확인 필요.", "빅테크 실적(내일)", "Microsoft, Meta, Tesla 실적 발표 예정.", "한국 설 연휴", "KOSPI는 설 연휴로 쉬고 있습니다."),
    ("2025-01-29",
     '<strong>연준 금리 동결, 빅테크 실적은 혼조.</strong><br><br>연준이 예상대로 금리를 동결(4.25~4.50%)했습니다. 파월 의장은 "금리 인하를 서두르지 않겠다"고 밝혔습니다. S&P500 <span class="hl-down">-0.47%</span>, NASDAQ <span class="hl-down">-0.51%</span>로 소폭 하락.<br><br>Tesla <span class="hl-down">-2.26%</span>, NVIDIA <span class="hl-down">-4.10%</span>로 기술주가 다시 약세. Microsoft 실적은 양호했지만 AI 투자 비용 우려로 시간외 하락. 환율이 1,443원으로 <span class="hl-warn">+1.79%</span> 급등(원화 약세)해 주의가 필요합니다.',
     [("이벤트", "FOMC 금리 동결", "4.25~4.50% 유지", "", "예상대로"), ("발언", "파월 '서두르지 않겠다'", "금리 인하 시기 불투명", "hl-warn", "매파적 발언"), ("실적", "빅테크 혼조", "Microsoft 양호, 하지만 AI 비용 우려", "hl-down", "기대 vs 현실"), ("한국", "원화 급락", "환율 1,443원 +1.79%", "hl-warn", "원화 약세")],
     "verdict-mixed", "보합(설연휴)", "verdict-down", "약세", "verdict-down", "소폭 하락",
     "금리 인하 시기 불확실", "파월의 매파적 발언으로 올해 금리 인하가 1~2회에 그칠 수 있습니다.", "AI 투자 비용 우려", "빅테크의 AI 투자가 실적으로 돌아오기까지 시간이 걸릴 수 있습니다.", "원화 약세 가속", "환율 1,443원은 우려 수준입니다.", "내일 Apple 실적", "Apple 실적이 기술주 방향을 결정할 것입니다."),
    ("2025-01-31",
     '<strong>1월 마지막 날, NVIDIA -3.67%로 불안한 마감.</strong><br><br>2025년 1월이 끝났습니다. S&P500 <span class="hl-down">-0.50%</span>(6,041), KOSPI <span class="hl-down">-0.77%</span>(2,517)로 마감. NVIDIA <span class="hl-down">-3.67%</span>, 삼성전자 <span class="hl-down">-2.42%</span>로 반도체주가 여전히 DeepSeek 여파에서 벗어나지 못하고 있습니다.<br><br>1월 한 달을 돌아보면: S&P500은 +2.7% 상승, KOSPI는 +4.9% 상승으로 나쁘지 않은 출발이었습니다. 하지만 월말에 DeepSeek 충격과 관세 불안으로 분위기가 무거워졌습니다. 2월에는 관세 정책 구체화와 AI 산업 재평가가 핵심 이슈가 될 것입니다.',
     [("1월 총평", "혼조의 한 달", "상반기 강세, 하반기 충격", "", "롤러코스터"), ("DeepSeek", "AI 패러다임 변화", "저비용 AI 등장으로 반도체 재평가", "hl-warn", "불확실성"), ("관세", "트럼프 관세 임박", "2월 관세 시행 가능성 높아짐", "hl-warn", "무역 불안"), ("월말", "불안한 마감", "NVIDIA -3.67%, 삼성 -2.42%", "hl-down", "약세 마감")],
     "verdict-down", "약세", "verdict-mixed", "혼조", "verdict-down", "하락",
     "2월 관세 시행 가능성", "트럼프가 2/1부터 중국, 멕시코, 캐나다에 관세를 부과할 수 있습니다.", "DeepSeek 후폭풍", "AI 반도체 수요 전망 재평가가 계속될 것입니다.", "연준 금리 인하 불투명", "파월의 매파적 발언으로 상반기 금리 인하 기대가 크게 줄었습니다.", "KOSPI 월간 +4.9%", "좋은 출발이었지만, 월말 하락세가 이어지면 2월이 걱정됩니다."),
    # February dates
    ("2025-02-10",
     '<strong>관세 충격 후 시장이 안정을 찾고 있습니다.</strong><br><br>2월 첫째 주, 트럼프가 중국에 10% 추가 관세를 부과하면서 시장이 출렁였지만, 오늘은 안정을 되찾고 있습니다. S&P500 <span class="hl-up">+0.67%</span>(6,066), NASDAQ <span class="hl-up">+0.98%</span>. Broadcom <span class="hl-up">+4.52%</span>, 삼성전자 <span class="hl-up">+3.54%</span>로 반도체주 회복세.<br><br>금값은 <span class="hl-up">+1.64%</span>($2,914)로 사상 최고치를 경신했습니다. 관세 불확실성 속 안전자산 수요가 폭발적입니다. 원/달러 환율은 1,451원으로 <span class="hl-warn">+0.59%</span>(원화 약세). 관세 영향으로 한국 수출 기업 우려가 지속되고 있습니다.',
     [("배경", "관세 시행 중", "중국 10% 추가, 멕시코/캐나다 유예", "hl-warn", "무역 긴장"), ("반응", "시장 안정화", "첫 충격 후 적응 단계", "up", "S&P +0.67%"), ("반도체", "회복 조짐", "Broadcom +4.5%, 삼성 +3.5%", "up", "저가매수"), ("안전자산", "금 사상 최고", "$2,914 역대 최고치", "up", "불확실성 반영")],
     "verdict-mixed", "보합", "verdict-mixed", "혼조", "verdict-up", "상승",
     "관세 확대 가능성", "멕시코/캐나다 관세 유예가 끝나면 추가 충격 가능.", "금값 사상 최고의 의미", "안전자산이 오른다는 것은 불확실성이 크다는 신호.", "미국 CPI 발표(2/12)", "물가가 높으면 금리 인하가 더 멀어집니다.", "한국 환율 1,451원", "관세 영향으로 원화 약세 지속 우려."),
    ("2025-02-11",
     '<strong>Tesla -6.34% 급락, 미국 기술주에 또다시 한파.</strong><br><br>S&P500은 <span class="hl-up">+0.03%</span>로 거의 변동 없었지만, Tesla가 <span class="hl-down">-6.34%</span> 급락했습니다. 유럽 판매 부진과 일론 머스크의 정치 활동에 대한 반감이 원인입니다. KOSPI는 <span class="hl-up">+0.71%</span>(2,539)로 반등. Apple <span class="hl-up">+2.18%</span>.<br><br>금리가 4.54%로 소폭 올랐고, 구리(Copper)가 <span class="hl-down">-2.26%</span> 하락하며 글로벌 경기 둔화 우려를 반영했습니다.',
     [("충격", "Tesla -6.34%", "유럽 판매 부진 + 머스크 리스크", "hl-down", "전기차 우려"), ("미국", "S&P 보합", "+0.03%로 거의 변동 없음", "", "관망"), ("한국", "KOSPI 반등", "+0.71%, 삼성전자 강세", "up", "회복세"), ("경기", "구리 -2.26%", "글로벌 경기 둔화 신호", "hl-down", "원자재 약세")],
     "verdict-up", "상승", "verdict-mixed", "혼조", "verdict-mixed", "보합",
     "Tesla 추가 하락 가능성", "유럽/중국 판매 부진이 계속되면 실적에 타격.", "내일 CPI 발표", "물가 데이터가 금리 방향을 결정합니다.", "구리 가격 하락", "경기 둔화의 선행지표일 수 있습니다.", "관세 2차 파동 우려", "멕시코/캐나다 관세 유예 기한 접근 중."),
    ("2025-02-12",
     '<strong>CPI 예상 상회! 물가가 다시 걱정됩니다.</strong><br><br>미국 1월 CPI가 예상보다 높게 나왔습니다. 10년 국채금리가 <span class="hl-warn">4.64%</span>로 <span class="hl-warn">+2.20%</span> 급등하면서 S&P500은 <span class="hl-down">-0.27%</span> 하락. 하지만 KOSPI는 <span class="hl-up">+0.37%</span>(2,548)로 선방했고, 홍콩 항셍(HSI)이 <span class="hl-up">+2.64%</span>로 강세.<br><br>WTI 원유는 <span class="hl-down">-2.66%</span>($71.37)로 급락. 높은 물가 &rarr; 금리 인하 지연 &rarr; 경기 둔화 우려로 에너지 수요 감소가 예상되었습니다. Tesla <span class="hl-up">+2.44%</span>는 어제의 급락에서 반등했습니다.',
     [("촉매", "CPI 예상 상회", "물가 둔화 기대 무너짐", "hl-warn", "인플레 우려"), ("반응", "금리 급등", "10년 4.64% +2.20%", "hl-warn", "금리 인하 후퇴"), ("결과", "미국 소폭 하락", "S&P -0.27%", "hl-down", "경기 우려"), ("에너지", "원유 급락", "WTI -2.66%", "down", "수요 감소 우려")],
     "verdict-up", "상승", "verdict-mixed", "혼조", "verdict-down", "소폭 하락",
     "물가 재상승 우려", "CPI가 예상보다 높아 연준 금리 인하가 더 늦어질 수 있습니다.", "금리 4.64% 재상승", "물가 우려로 금리가 다시 오르면 성장주에 부담.", "원유 급락의 의미", "경기 둔화 신호일 수 있습니다.", "관세의 물가 영향", "관세가 물가를 더 올릴 수 있어 이중 부담."),
    ("2025-02-13",
     '<strong>안도 반등! Tesla +5.77%로 시장 분위기 전환.</strong><br><br>어제의 CPI 충격에서 빠르게 회복했습니다. S&P500 <span class="hl-up">+1.04%</span>(6,115), NASDAQ <span class="hl-up">+1.50%</span>. Tesla <span class="hl-up">+5.77%</span>, NVIDIA <span class="hl-up">+3.16%</span>로 기술주가 강세. "CPI는 한 달 데이터일 뿐, 큰 추세는 물가 둔화"라는 낙관론이 우세해졌습니다.<br><br>KOSPI도 <span class="hl-up">+1.36%</span>(2,583)로 동반 상승. 10년 금리가 4.53%로 다시 내려오면서 시장이 안도했습니다. VIX 15.1로 공포감은 낮은 수준입니다.',
     [("어제", "CPI 충격", "물가 예상 상회로 급락", "hl-down", "과도한 반응"), ("오늘", "안도 반등", "큰 추세는 물가 둔화라는 판단", "up", "저가매수"), ("기술주", "강한 회복", "Tesla +5.8%, NVIDIA +3.2%", "up", "NASDAQ +1.50%"), ("한국", "동반 상승", "KOSPI +1.36%", "up", "2,583")],
     "verdict-up", "강세", "verdict-up", "상승", "verdict-up", "급등",
     "물가 추세 확인 필요", "다음 달 CPI도 높으면 금리 인하가 올해 없을 수도 있습니다.", "관세의 물가 전이 효과", "관세가 수입품 가격을 올려 CPI를 더 높일 수 있습니다.", "반도체 실적 시즌", "NVIDIA 실적(2/26)이 AI 투자 방향을 결정할 것.", "VIX 15.1 안정", "시장은 아직 크게 걱정하지 않고 있습니다."),
    ("2025-02-14",
     '<strong>밸런타인데이, 시장은 달콤한 보합.</strong><br><br>S&P500 <span class="hl-down">-0.01%</span>, NASDAQ <span class="hl-up">+0.41%</span>로 거의 변동 없이 한 주를 마감했습니다. KOSPI <span class="hl-up">+0.31%</span>(2,591). VIX 14.8로 시장은 매우 안정적입니다. 홍콩 항셍이 <span class="hl-up">+3.69%</span>로 폭등했는데, 중국 AI 기업(DeepSeek 포함)에 대한 기대감이 작용했습니다.<br><br>금값은 <span class="hl-down">-1.45%</span>($2,884)로 차익실현. 원/달러 1,439원으로 <span class="hl-up">-0.92%</span>(원화 강세). 전반적으로 평화로운 밸런타인데이 시장이었습니다.',
     [("배경", "한 주 마무리", "큰 이벤트 없는 금요일", "", "조용한 마감"), ("중국", "항셍 +3.69%", "중국 AI 기대감 폭발", "up", "DeepSeek 효과"), ("한국", "KOSPI +0.31%", "안정적 상승", "up", "2,591"), ("안전자산", "금 차익실현", "-1.45%", "down", "위험선호 회복")],
     "verdict-up", "상승", "verdict-mixed", "혼조", "verdict-mixed", "보합",
     "다음 주 NVIDIA 실적(2/26)", "AI 투자의 향방을 결정할 최대 이벤트.", "관세 확대 우려", "멕시코/캐나다 관세 유예가 끝날 수 있습니다.", "중국 AI 부상", "DeepSeek 효과로 중국 기술주가 부상하고 있습니다.", "원화 강세 지속", "1,439원은 1월 대비 크게 개선된 수준."),
    ("2025-02-17",
     '<strong>미국 휴장(대통령의 날), 아시아와 유럽만 거래.</strong><br><br>미국 Presidents Day 공휴일로 뉴욕 증시가 쉬었습니다. KOSPI <span class="hl-up">+0.75%</span>(2,610)로 상승하며 연초 이후 최고치를 기록! KOSDAQ <span class="hl-up">+1.61%</span>, DAX <span class="hl-up">+1.26%</span>로 아시아/유럽 모두 강세.<br><br>원/달러 환율 1,433원으로 <span class="hl-up">-0.43%</span>(원화 강세 지속). 달러 약세가 이어지면서 전 세계 통화가 강세를 보이고 있습니다. 한국 시장이 최근 2주간 꾸준히 오르고 있어 투자자 심리가 개선되고 있습니다.',
     [("배경", "미국 휴장", "대통령의 날 공휴일", "", "거래 없음"), ("아시아", "KOSPI 최고치", "+0.75% 연초 이후 최고", "up", "2,610"), ("유럽", "DAX 강세", "+1.26% 유럽 경기 기대", "up", "동반 상승"), ("환율", "원화 강세", "1,433원 달러 약세 반영", "up", "수입 유리")],
     "verdict-up", "강세", "verdict-up", "강세", "verdict-mixed", "휴장",
     "내일 미국 시장 반응", "휴장 후 첫 거래일 반응에 주목.", "NVIDIA 실적(2/26)", "AI 투자의 핵심 이벤트가 다가오고 있습니다.", "KOSPI 2,610 고점 부담", "너무 빨리 올라 조정 가능성도 있습니다.", "관세 리스크 상존", "트럼프 관세 정책의 불확실성은 계속됩니다."),
    ("2025-02-18",
     '<strong>KOSPI 연초 이후 최고! 삼성전자가 이끌다.</strong><br><br>KOSPI <span class="hl-up">+0.63%</span>(2,627)로 상승세 지속. 삼성전자 <span class="hl-up">+1.61%</span>가 견인했습니다. S&P500 <span class="hl-up">+0.24%</span>, NASDAQ <span class="hl-up">+0.07%</span>로 미국도 소폭 상승. 금값이 <span class="hl-up">+1.66%</span>($2,932)로 다시 사상 최고치에 접근!<br><br>천연가스 <span class="hl-up">+7.57%</span> 폭등, META <span class="hl-down">-2.76%</span>, Broadcom <span class="hl-down">-1.94%</span>. 전반적으로 "서서히 오르는" 안정적 상승세이지만, 다음 주 NVIDIA 실적이 변수입니다.',
     [("한국", "KOSPI 상승세", "+0.63% 삼성전자 견인", "up", "2,627"), ("미국", "소폭 상승", "S&P +0.24%", "up", "안정"), ("안전자산", "금 최고치 접근", "$2,932 +1.66%", "up", "불확실성 속 강세"), ("에너지", "천연가스 폭등", "+7.57%", "hl-warn", "기상 변동")],
     "verdict-up", "상승", "verdict-mixed", "혼조", "verdict-up", "소폭 상승",
     "NVIDIA 실적(2/26)", "다음 주 가장 중요한 이벤트.", "금값 사상 최고 접근", "관세 + 지정학 불확실성이 금 수요를 밀어올리고 있습니다.", "META -2.76% 약세", "소셜미디어 광고 시장 우려.", "한국 시장 모멘텀", "KOSPI가 2,600선을 유지할 수 있을지 관건."),
    ("2025-02-19",
     '<strong>KOSPI +1.70%! 삼성전자 +3.16%로 한국 시장 폭발.</strong><br><br>KOSPI가 <span class="hl-up">+1.70%</span>(2,672)로 급등했습니다. 삼성전자 <span class="hl-up">+3.16%</span>가 최대 공신. AI 반도체 수요 기대와 외국인 매수가 겹치면서 한국 시장이 독보적으로 강했습니다.<br><br>미국 S&P500은 <span class="hl-up">+0.24%</span>, 유럽 DAX <span class="hl-down">-1.80%</span>, STOXX50 <span class="hl-down">-1.31%</span>로 유럽은 약세. 한국과 유럽이 정반대로 움직인 하루입니다. 천연가스 <span class="hl-up">+6.81%</span> 또 폭등.',
     [("한국", "KOSPI +1.70%", "삼성전자 +3.16% 주도", "up", "2,672"), ("미국", "소폭 상승", "S&P +0.24%", "up", "안정"), ("유럽", "약세", "DAX -1.80%", "hl-down", "경기 우려"), ("에너지", "천연가스 +6.81%", "한파 지속 효과", "hl-warn", "변동성")],
     "verdict-up", "급등", "verdict-down", "약세", "verdict-up", "소폭 상승",
     "NVIDIA 실적(2/26)", "일주일 앞으로 다가왔습니다.", "유럽 약세의 의미", "유럽 경기 둔화 우려가 커지고 있습니다.", "한국 시장 과열?", "너무 빠른 상승은 조정 위험이 있습니다.", "관세 리스크", "트럼프 관세 추가 확대 가능성."),
    ("2025-02-20",
     '<strong>시장 전체가 쉬어가는 날. 조정 시작?</strong><br><br>연이틀 상승하던 시장이 쉬어갑니다. S&P500 <span class="hl-down">-0.43%</span>, NASDAQ <span class="hl-down">-0.47%</span>, KOSPI <span class="hl-down">-0.65%</span>. 닛케이 <span class="hl-down">-1.24%</span>. 전 세계 주요 지수가 동반 하락했습니다.<br><br>금값만 <span class="hl-up">+0.71%</span>($2,940)로 사상 최고치 경신 중. Silver <span class="hl-up">+1.37%</span>, 구리 <span class="hl-up">+1.12%</span>로 원자재가 상대적으로 강세. "주식에서 원자재로" 돈이 이동하는 것일 수 있습니다.',
     [("배경", "상승 피로감", "연이틀 상승 후 차익실현", "hl-down", "조정"), ("주식", "동반 하락", "S&P -0.43%, KOSPI -0.65%", "hl-down", "전세계 약세"), ("원자재", "금 사상 최고", "$2,940", "up", "안전 수요"), ("흐름", "자산 순환", "주식 &rarr; 원자재로 자금 이동?", "hl-warn", "로테이션")],
     "verdict-down", "하락", "verdict-down", "하락", "verdict-down", "하락",
     "NVIDIA 실적(2/26)", "이번 주 최대 이벤트. AI 투자 방향 결정.", "글로벌 동반 조정", "전 세계 시장이 함께 빠지면 추세 전환 가능성.", "금값 $2,940 사상 최고", "불확실성이 극대화되고 있다는 신호.", "관세 영향 가시화", "무역 데이터에서 관세 영향이 나타나기 시작."),
    ("2025-02-21",
     '<strong>S&P500 -1.71%, NASDAQ -2.20% &mdash; 주간 급락으로 마감.</strong><br><br>금요일, 시장이 크게 빠졌습니다. S&P500 <span class="hl-down">-1.71%</span>(6,013), NASDAQ <span class="hl-down">-2.20%</span>. Tesla <span class="hl-down">-4.68%</span>, NVIDIA <span class="hl-down">-4.05%</span>, Broadcom <span class="hl-down">-3.56%</span>. 관세 확대 우려와 경기 둔화 우려가 겹치면서 투자자들이 일제히 주식을 팔았습니다.<br><br>반면 홍콩 항셍(HSI) <span class="hl-up">+3.99%</span>로 폭등. 중국 기술주가 DeepSeek 효과로 강세를 보이며, 미국 기술주와 정반대 움직임을 보였습니다. VIX 18.2로 불안감 상승 중.',
     [("원인", "관세+경기 우려", "무역 갈등 심화 + 경기 둔화 신호", "hl-down", "이중 부담"), ("결과", "기술주 급락", "NVIDIA -4%, Tesla -4.7%", "hl-down", "패닉 매도"), ("반대로", "중국 폭등", "항셍 +3.99% DeepSeek 효과", "up", "역전 현상"), ("VIX", "불안 상승", "18.2로 경계 수준 접근", "hl-warn", "공포 확산")],
     "verdict-mixed", "보합", "verdict-mixed", "혼조", "verdict-down", "급락",
     "주말 관세 뉴스", "주말 사이에 관세 관련 추가 발표가 나올 수 있습니다.", "NVIDIA 실적(다음 주 수)", "AI 투자의 미래가 달린 실적 발표.", "VIX 20 접근", "20을 넘으면 시장 불안이 공식화됩니다.", "미중 기술 디커플링", "미국 기술주 하락 vs 중국 기술주 상승이 심화."),
    ("2025-02-24",
     '<strong>월요일 추가 하락. S&P500 -0.50%, NASDAQ -1.21%.</strong><br><br>지난 금요일의 급락이 이어졌습니다. S&P500 <span class="hl-down">-0.50%</span>(5,983), NASDAQ <span class="hl-down">-1.21%</span>. TSMC <span class="hl-down">-3.32%</span>, Broadcom <span class="hl-down">-4.91%</span>로 반도체주 약세가 지속되고 있습니다. KOSPI <span class="hl-down">-0.35%</span>(2,645).<br><br>금값 $2,948로 사상 최고치 갱신 중. 국채금리 4.39%로 하락하면서 "경기 둔화 &rarr; 안전자산으로" 자금 이동이 뚜렷해지고 있습니다. 수요일 NVIDIA 실적이 분수령이 될 것입니다.',
     [("배경", "금요일 급락 연장", "관세+경기 우려 지속", "hl-down", "하락세"), ("반도체", "추가 약세", "TSMC -3.3%, Broadcom -4.9%", "hl-down", "AI 우려"), ("안전자산", "금 사상 최고", "$2,948", "up", "경기 우려 반영"), ("대기", "NVIDIA 실적(수)", "수요일이 분수령", "hl-warn", "긴장")],
     "verdict-down", "하락", "verdict-mixed", "혼조", "verdict-down", "하락",
     "NVIDIA 실적(수요일)", "AI 투자의 미래를 결정할 가장 중요한 이벤트.", "경기 둔화 신호 증가", "국채금리 하락, 원유 하락이 경기 둔화를 시사.", "관세 확대 가능성", "트럼프가 추가 관세를 예고하고 있습니다.", "금값 $2,950 접근", "역사적 수준의 불확실성을 반영."),
    ("2025-02-25",
     '<strong>Tesla -8.39%! 관세 우려에 시장 추가 하락.</strong><br><br>S&P500 <span class="hl-down">-0.47%</span>(5,955), NASDAQ <span class="hl-down">-1.35%</span>. Tesla <span class="hl-down">-8.39%</span> 폭락이 가장 충격적입니다. 트럼프 관세 확대 우려와 유럽 판매 부진이 겹치면서 Tesla에 집중 매도가 쏟아졌습니다.<br><br>NVIDIA <span class="hl-down">-2.80%</span>, Broadcom <span class="hl-down">-2.59%</span>. KOSPI <span class="hl-down">-0.57%</span>(2,630). 닛케이 <span class="hl-down">-1.39%</span>. 내일 NVIDIA 실적 발표를 앞두고 극도의 긴장감이 감돌고 있습니다.',
     [("원인", "관세 확대 우려", "트럼프 추가 관세 시사", "hl-down", "무역 공포"), ("충격", "Tesla -8.39%", "유럽 판매 부진 + 관세 우려", "hl-down", "폭락"), ("확산", "기술주 전반 약세", "NVIDIA -2.8%, Broadcom -2.6%", "hl-down", "동반 하락"), ("대기", "내일 NVIDIA 실적", "AI의 미래가 달린 발표", "hl-warn", "D-1")],
     "verdict-down", "하락", "verdict-mixed", "혼조", "verdict-down", "급락",
     "내일 NVIDIA 실적", "AI 투자의 향방을 결정할 최대 이벤트.", "Tesla 위기", "8% 급락은 심각한 수준. 추가 하락 가능.", "관세 확대 공포", "멕시코/캐나다 관세가 현실화되면 충격 클 것.", "VIX 19.4 경계", "20 돌파 임박. 시장 불안 수위 높아짐."),
    ("2025-02-26",
     '<strong>NVIDIA 실적 대기 속, 시장은 숨 고르기.</strong><br><br>NVIDIA 실적 발표를 오늘 장 마감 후 앞두고 시장은 조용했습니다. S&P500 <span class="hl-up">+0.01%</span>(5,956), KOSPI <span class="hl-up">+0.41%</span>(2,641). Broadcom <span class="hl-up">+5.13%</span>, NVIDIA <span class="hl-up">+3.67%</span>로 기대감 속 반등.<br><br>반면 Apple <span class="hl-down">-2.70%</span>, Tesla <span class="hl-down">-3.96%</span>로 일부 대형주는 계속 약세. 홍콩 항셍 <span class="hl-up">+3.27%</span>로 중국 기술주는 여전히 강세. 오늘 밤 NVIDIA 실적이 시장 방향을 결정합니다.',
     [("대기", "NVIDIA 실적 D-Day", "장 마감 후 발표 예정", "hl-warn", "긴장"), ("기대", "반도체주 반등", "NVIDIA +3.67%, Broadcom +5.13%", "up", "기대감"), ("약세", "Apple/Tesla 하락", "관세 우려 지속", "hl-down", "개별 악재"), ("중국", "항셍 +3.27%", "중국 AI 강세 지속", "up", "대안 부상")],
     "verdict-up", "상승", "verdict-mixed", "혼조", "verdict-mixed", "보합",
     "NVIDIA 실적 결과", "오늘 밤 발표. 예상 상회 시 AI 랠리 재개, 하회 시 추가 급락 가능.", "관세 영향 지속", "무역 불확실성이 시장 전반을 짓누르고 있습니다.", "Apple -2.7%", "중국 시장 우려가 Apple에 타격.", "금값 $2,917", "여전히 사상 최고 수준 유지."),
    ("2025-02-27",
     '<strong>NVIDIA 실적 후 반도체 폭락! NVIDIA -8.48%.</strong><br><br>NVIDIA가 4분기 실적을 발표했습니다. 매출은 예상을 상회했지만, 이익률 전망이 기대에 못 미치면서 시간외 급락 &rarr; 오늘 <span class="hl-down">-8.48%</span>. TSMC <span class="hl-down">-6.95%</span>, Broadcom <span class="hl-down">-7.11%</span>로 반도체 생태계 전체가 충격.<br><br>NASDAQ <span class="hl-down">-2.78%</span>, S&P500 <span class="hl-down">-1.59%</span>. VIX <span class="hl-warn">21.1</span>로 20을 돌파하며 공식적으로 "불안한 시장"에 진입했습니다. KOSPI <span class="hl-down">-0.73%</span>(2,622). 관세 우려까지 겹치면서 시장이 이중 압박을 받고 있습니다.',
     [("촉매", "NVIDIA 실적 실망", "매출 양호하나 이익률 전망 부진", "hl-down", "기대 하회"), ("확산", "반도체 폭락", "TSMC -7%, Broadcom -7%", "hl-down", "생태계 충격"), ("결과", "NASDAQ -2.78%", "기술주 중심 급락", "hl-down", "S&P -1.59%"), ("공포", "VIX 21.1", "20 돌파, 불안 시장 진입", "hl-warn", "공포 확산")],
     "verdict-down", "하락", "verdict-mixed", "혼조", "verdict-down", "급락",
     "반도체 추가 하락 가능성", "NVIDIA 실망으로 AI 투자 재평가가 불가피합니다.", "VIX 20 돌파", "시장이 공식적으로 불안 구간에 진입했습니다.", "관세 + 실적 이중 충격", "무역 불확실성과 실적 실망이 동시에 시장을 압박.", "내일 PCE 물가 발표", "연준이 중시하는 물가 지표. 높으면 금리 인하 더 멀어짐."),
    ("2025-02-28",
     '<strong>2월 마지막 날, KOSPI -3.39% 폭락.</strong><br><br>2월 마지막 거래일, KOSPI가 <span class="hl-down">-3.39%</span>(2,533)로 폭락했습니다. 트럼프가 3/4부터 멕시코, 캐나다에 25% 관세, 중국에 추가 10% 관세를 부과한다고 발표한 것이 직격탄이었습니다. 닛케이 <span class="hl-down">-2.88%</span>, 홍콩 항셍 <span class="hl-down">-3.28%</span>로 아시아 전체가 패닉.<br><br>반면 미국 S&P500 <span class="hl-up">+1.59%</span>, NASDAQ <span class="hl-up">+1.63%</span>로 반등! NVIDIA <span class="hl-up">+3.97%</span>, Tesla <span class="hl-up">+3.91%</span>. 아시아가 공포에 빠진 사이 미국은 "이미 반영되었다"며 저가매수가 들어온 것입니다. 원/달러 1,450원으로 <span class="hl-warn">+1.08%</span> 급등(원화 급락).',
     [("충격", "관세 발표", "3/4부터 멕시코/캐나다 25%, 중국 추가 10%", "hl-down", "무역전쟁 본격화"), ("아시아", "패닉 매도", "KOSPI -3.39%, 닛케이 -2.88%", "hl-down", "아시아 폭락"), ("미국", "역발상 반등", "이미 반영론 + 저가매수", "up", "S&P +1.59%"), ("환율", "원화 급락", "1,450원 +1.08%", "hl-warn", "수출 우려")],
     "verdict-down", "폭락", "verdict-down", "하락", "verdict-up", "반등",
     "3/4 관세 시행", "다음 주 화요일부터 멕시코/캐나다 25%, 중국 추가 10% 관세 시행.", "아시아 시장 추가 하락 가능", "KOSPI -3.39% 폭락 후 월요일 추가 매도 가능.", "미국 vs 아시아 디커플링", "같은 뉴스에 미국은 상승, 아시아는 하락하는 괴리 심화.", "원화 1,450원", "관세 충격으로 원화가 급락. 환율 1,450원은 경계 수준.")
]:
    sessions = [
        ("asia", "&#127471;&#127477;", "아시아", "09:00~15:30", asia_v, asia_l,
         [f'데이터 탭의 수치를 참고하세요'], [("KOSPI", "데이터 참조", "")]),
        ("europe", "&#127466;&#127482;", "유럽", "17:00~01:30", eur_v, eur_l,
         [f'데이터 탭의 수치를 참고하세요'], [("DAX", "데이터 참조", "")]),
        ("us", "&#127482;&#127480;", "미국", "23:30~06:00", us_v, us_l,
         [f'데이터 탭의 수치를 참고하세요'], [("S&P 500", "데이터 참조", "")])
    ]

    insights_list = [
        ("rgba(59,110,230,0.1)", "var(--accent)", "핵심", causal[0][1],
         f'{causal[0][2]} 오늘 시장의 핵심 동력이었습니다.',
         [(causal[0][1], causal[0][4], causal[0][3])]),
        ("rgba(212,139,7,0.1)", "var(--warn)", "흐름", causal[1][1],
         f'{causal[1][2]}',
         [(causal[1][1], causal[1][4], causal[1][3])]),
        ("rgba(211,84,0,0.1)", "var(--oil)", "영향", causal[2][1],
         f'{causal[2][2]}',
         [(causal[2][1], causal[2][4], causal[2][3])]),
        ("rgba(217,48,79,0.1)", "var(--down)", "전망", causal[3][1],
         f'{causal[3][2]}',
         [(causal[3][1], causal[3][4], causal[3][3])])
    ]

    cross_nodes = [[[
        (causal[0][1], causal[0][4], causal[0][2][:20], causal[0][3]),
        ("&rarr;", "영향"),
        (causal[1][1], causal[1][4], causal[1][2][:20], causal[1][3]),
        ("&rarr;", "결과"),
        (causal[2][1], causal[2][4], causal[2][2][:20], causal[2][3])
    ]]]

    risks_list = [
        ("high", risk1, risk2),
        ("high", risk3, risk4) if "높음" not in risk4 else ("med", risk3, risk4),
    ]
    # Add remaining risks if we have 4
    risks_list = [
        ("high", risk1, risk2),
        ("med", risk3, risk4),
    ]

    STORIES[date] = make_story(hero, causal, sessions, cross_nodes, insights_list, risks_list)


def inject_all():
    base = "/Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/output"
    processed = 0
    skipped = 0

    for month_dir in ["2025-01", "2025-02"]:
        dir_path = os.path.join(base, month_dir)
        if not os.path.isdir(dir_path):
            continue
        for fname in sorted(os.listdir(dir_path)):
            if not fname.endswith('.html'):
                continue
            fpath = os.path.join(dir_path, fname)
            date_str = fname.replace('.html', '')

            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()

            if '<!-- STORY_CONTENT_PLACEHOLDER -->' not in content:
                skipped += 1
                continue

            if date_str not in STORIES:
                print(f"SKIP {date_str}: no story defined")
                skipped += 1
                continue

            new_content = content.replace('<!-- STORY_CONTENT_PLACEHOLDER -->', STORIES[date_str])
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(new_content)

            processed += 1
            print(f"OK {date_str}")

    print(f"\nDone: {processed} processed, {skipped} skipped")


if __name__ == '__main__':
    inject_all()
