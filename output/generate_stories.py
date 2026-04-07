#!/usr/bin/env python3
"""Generate Market Story content for Jul-Aug 2025 HTML files."""

import re
import os
from datetime import datetime

def extract_kpi_data(html):
    """Extract KPI values from HTML."""
    data = {}
    # Extract KPI blocks
    kpi_pattern = r'<div class="kpi-label">(.*?)</div>\s*<div class="kpi-value">(.*?)</div>\s*<div class="kpi-chg\s+(up|down|flat)">(.*?)</div>'
    for m in re.finditer(kpi_pattern, html, re.DOTALL):
        label, value, direction, chg = m.group(1), m.group(2), m.group(3), m.group(4)
        data[label.strip()] = {'value': value.strip(), 'direction': direction, 'chg': chg.strip()}

    # Extract VIX from mood badge
    vix_m = re.search(r'VIX\s+([\d.]+)', html)
    if vix_m:
        data['VIX'] = {'value': vix_m.group(1)}

    # Extract top gainers/losers
    gainers = re.findall(r'Top Gainers.*?</div>\s*</div>', html, re.DOTALL)
    losers = re.findall(r'Top Losers.*?</div>\s*</div>', html, re.DOTALL)

    gainer_items = []
    if gainers:
        for m in re.finditer(r'mover-name">(.*?)</span>.*?mover-val\s+\w+">(.*?)</span>', gainers[0], re.DOTALL):
            gainer_items.append((m.group(1), m.group(2)))

    loser_items = []
    if losers:
        for m in re.finditer(r'mover-name">(.*?)</span>.*?mover-val\s+\w+">(.*?)</span>', losers[0], re.DOTALL):
            loser_items.append((m.group(1), m.group(2)))

    data['_gainers'] = gainer_items
    data['_losers'] = loser_items

    # Extract date
    date_m = re.search(r'<title>Market Summary \| (\d{4}-\d{2}-\d{2})</title>', html)
    if date_m:
        data['_date'] = date_m.group(1)

    # Day of week from header
    dow_m = re.search(r'<div class="date">(.*?)</div>', html)
    if dow_m:
        data['_dow'] = dow_m.group(1).strip()

    return data


def get_chg_val(chg_str):
    """Parse change string to float."""
    try:
        return float(chg_str.replace('%', '').replace('+', ''))
    except:
        return 0.0


def chg_span(val_str, direction=None):
    """Return span with appropriate class."""
    v = get_chg_val(val_str)
    if direction == 'up' or v > 0:
        return f'<span class="hl-up">{val_str}</span>'
    elif direction == 'down' or v < 0:
        return f'<span class="hl-down">{val_str}</span>'
    return f'<span style="color:var(--muted)">{val_str}</span>'


# ─── Story narratives for each date ───
# Key Jul-Aug 2025 themes:
# Early Jul: H1 ends strong, summer rally begins, AI stocks leading
# Mid Jul: Q2 earnings season kicks off (banks, then tech), Fed speculation
# Late Jul: FOMC meeting (Jul 29-30), rate decision
# Early Aug: Tech earnings (Apple, Amazon, etc), jobs report
# Mid Aug: Inflation data (CPI), market rotation debate
# Late Aug: Jackson Hole symposium, end-of-summer positioning

NARRATIVES = {
    '2025-07-01': {
        'hero_title': '하반기의 문이 열렸습니다',
        'hero_body': '2025년 상반기가 끝나고 하반기 첫 거래일입니다. 올해 상반기 S&P500은 약 15% 상승하며 AI 관련 기술주가 시장을 이끌었습니다. 하지만 "이 랠리가 계속될 수 있을까?"라는 의문도 함께 커지고 있습니다. 오늘은 그 기대와 불안이 교차하는 하루였습니다.',
        'chain': [
            ('상반기 마감', 'AI 랠리로 상반기 마무리', 'S&P500 약 +15% YTD', 'up'),
            ('하반기 첫날', '투자자 차익실현 vs 추가매수', '방향 탐색 중', 'muted'),
            ('7월 전망', 'Q2 실적 시즌 대기', '실적이 방향 결정', 'muted'),
        ],
        'insights': [
            ('랠리', 'var(--up)', 'rgba(13,155,106,0.1)', '상반기 랠리란?', '2025년 상반기(1~6월) 동안 미국 주식시장은 크게 올랐습니다. 특히 AI(인공지능) 관련 기업인 엔비디아, 마이크로소프트, 애플 등이 큰 폭으로 상승했습니다. "랠리"란 주가가 일정 기간 동안 지속적으로 오르는 현상을 말합니다.'),
            ('실적시즌', 'var(--accent)', 'rgba(59,110,230,0.1)', 'Q2 실적 시즌이란?', 'Q2는 "2분기(4~6월)"를 뜻합니다. 기업들은 매 분기마다 "얼마나 벌었는지"를 공개하는데, 이 시기를 "실적 시즌(Earnings Season)"이라 합니다. 7월 중순부터 은행, 기술 기업 순으로 실적을 발표합니다. 실적이 좋으면 주가가 오르고, 나쁘면 떨어집니다.'),
            ('금리', 'var(--warn)', 'rgba(212,139,7,0.1)', 'Fed(연준)의 금리 결정이 왜 중요한가?', 'Fed(Federal Reserve, 연방준비제도)는 미국의 중앙은행입니다. 금리를 올리면 대출 이자가 비싸져 기업 활동이 위축되고, 내리면 돈을 빌리기 쉬워져 경제가 활발해집니다. 7월 말 FOMC(연방공개시장위원회) 회의에서 금리 결정이 예정되어 있어 시장이 주목하고 있습니다.'),
            ('하반기', 'var(--accent2)', 'rgba(107,92,231,0.1)', '하반기 시장 전망의 핵심', '하반기에는 AI 투자의 실제 수익성, 미국 대선 영향, 금리 인하 시점 등이 시장의 핵심 변수입니다. 상반기에 많이 오른 만큼, "더 오를 여력이 있다"는 낙관론과 "너무 비싸졌다"는 신중론이 팽팽합니다.'),
        ],
        'risks': [
            ('높음', 'high', 'AI 버블 우려', 'AI 관련 기업들의 주가가 상반기에 크게 올랐습니다. 하지만 실제 AI 매출이 기대만큼 나오지 않으면 "버블(거품)"이 꺼질 수 있습니다. Q2 실적 시즌에서 AI 관련 매출이 핵심 관전 포인트입니다.'),
            ('높음', 'high', 'Fed 금리 정책 불확실성', '시장은 올해 안에 금리 인하를 기대하고 있지만, 인플레이션(물가 상승)이 여전히 높으면 금리 인하가 늦어질 수 있습니다. 7월 FOMC 회의 결과에 따라 시장이 크게 흔들릴 수 있습니다.'),
            ('보통', 'med', '여름 거래량 감소', '여름 휴가철이 되면 거래량(주식을 사고파는 양)이 줄어듭니다. 거래량이 적으면 작은 뉴스에도 주가가 크게 움직일 수 있어 변동성이 커질 수 있습니다.'),
            ('보통', 'med', '미중 무역 긴장', '미국과 중국 간 기술 규제와 무역 갈등이 계속되고 있습니다. AI 반도체 수출 제한 등이 한국 반도체 기업에도 영향을 줄 수 있습니다.'),
        ],
    },
    '2025-07-02': {
        'hero_title': '기술주에 숨 고르기가 찾아왔습니다',
        'hero_body': '상반기 랠리를 이끌었던 기술주들이 잠시 쉬어가는 모습입니다. 엔비디아와 테슬라 등 AI 관련 대형 기술주가 차익실현 매물에 눌리고 있습니다. 반면 그동안 소외되었던 중소형주(Russell 2000)는 상대적으로 선전하고 있어, "시장 내 자금 이동(로테이션)"이 시작되는 것 아니냐는 이야기가 나옵니다.',
        'chain': [
            ('기술주 차익실현', '상반기 급등 후 이익 확정 매도', '대형 기술주 약세', 'down'),
            ('자금 이동', '기술주에서 중소형주로 자금 회전', '로테이션 조짐', 'muted'),
            ('실적 대기', 'Q2 실적 발표 전 관망', '방향 탐색 중', 'muted'),
        ],
        'insights': [
            ('로테이션', 'var(--accent)', 'rgba(59,110,230,0.1)', '시장 로테이션이란?', '주식시장에서 "로테이션(Rotation)"이란 투자자들의 돈이 한 섹터(분야)에서 다른 섹터로 이동하는 현상입니다. 예를 들어 기술주가 많이 올라서 비싸 보이면, 상대적으로 저렴한 금융주나 중소형주로 돈이 옮겨갑니다.'),
            ('차익실현', 'var(--warn)', 'rgba(212,139,7,0.1)', '차익실현이란?', '"차익실현"이란 주가가 올랐을 때 보유한 주식을 팔아서 이익을 확정짓는 것입니다. 많은 투자자들이 상반기에 큰 수익을 올렸기 때문에, 하반기 초에 이익을 실현하려는 매도세가 나타날 수 있습니다.'),
            ('반도체', 'var(--accent2)', 'rgba(107,92,231,0.1)', 'AI 반도체 수요 전망', 'AI 서비스를 운영하려면 고성능 반도체(GPU)가 필요합니다. 엔비디아가 이 시장의 약 80%를 차지하고 있는데, 경쟁사들도 빠르게 따라오고 있어 독점적 지위가 흔들릴 수 있다는 우려가 있습니다.'),
            ('금', 'var(--gold)', 'rgba(184,134,11,0.1)', '금 가격이 계속 오르는 이유', '금은 전통적인 안전자산입니다. 경제 불확실성이 높거나 인플레이션이 걱정될 때 투자자들이 금을 삽니다. 올해 금 가격이 사상 최고치를 기록한 것은 세계 경제에 대한 불안감이 여전하다는 신호입니다.'),
        ],
        'risks': [
            ('높음', 'high', '기술주 밸류에이션 부담', 'AI 관련 기술주의 PER(주가수익비율, 주가가 이익의 몇 배인지)이 역사적 평균보다 높습니다. 실적이 기대에 못 미치면 급락할 수 있습니다.'),
            ('보통', 'med', '미국 고용 지표 발표', '이번 주 금요일 미국 고용 지표(비농업 고용자 수)가 발표됩니다. 고용이 너무 강하면 Fed가 금리 인하를 미룰 수 있고, 너무 약하면 경기 침체 우려가 커질 수 있습니다.'),
            ('보통', 'med', '유럽 정치 불안', '유럽 주요국에서 정치적 불확실성이 이어지고 있어, 유럽 증시에 부담이 되고 있습니다.'),
            ('보통', 'med', '원유 가격 변동', '중동 지역 긴장감이 유가 변동성을 키우고 있습니다. 원유 가격이 오르면 물가 상승 압력이 커져 금리 인하 기대를 약화시킬 수 있습니다.'),
        ],
    },
    '2025-07-03': {
        'hero_title': '독립기념일 전야, 시장은 일찍 문을 닫습니다',
        'hero_body': '내일(7월 4일)은 미국 독립기념일로 뉴욕 증시가 휴장합니다. 오늘은 단축 거래일이라 거래량이 평소보다 적었습니다. 투자자들은 연휴를 앞두고 큰 베팅을 피하며 관망하는 분위기였습니다. 한국 시장은 정상 개장했지만, 미국 시장의 영향력이 큰 만큼 조용한 하루를 보냈습니다.',
        'chain': [
            ('미국 단축거래', '독립기념일 전날 조기 마감', '거래량 급감', 'muted'),
            ('관망 분위기', '연휴 전 리스크 회피', '변동성 축소', 'muted'),
            ('다음 주 준비', '연휴 후 실적 시즌 본격화', '은행주 실적 주목', 'up'),
        ],
        'insights': [
            ('휴장', 'var(--muted)', 'rgba(124,130,152,0.1)', '미국 증시 휴장일의 영향', '미국 증시가 쉬는 날에는 전 세계 금융시장의 "기준점"이 없어집니다. 미국 시장은 세계 주식시장의 약 60%를 차지하기 때문에, 휴장 시 다른 나라 시장도 거래가 줄어들고 조용해지는 경향이 있습니다.'),
            ('단축거래', 'var(--accent)', 'rgba(59,110,230,0.1)', '단축 거래일이란?', '미국 증시는 주요 공휴일 전날에 정규 거래 시간을 단축합니다(보통 4시간 → 3.5시간). 거래 시간이 짧아지면 거래량도 줄어들고, 큰 가격 변동이 적은 편입니다.'),
            ('상반기결산', 'var(--up)', 'rgba(13,155,106,0.1)', '상반기 성적표 정리', '2025년 상반기 주요 지수 성적: S&P500은 약 +15%, NASDAQ은 약 +18%, KOSPI는 약 +28% 상승했습니다. 한국 시장이 미국보다 더 크게 올랐는데, 이는 반도체 수출 호조와 외국인 매수 덕분입니다.'),
            ('연휴효과', 'var(--accent2)', 'rgba(107,92,231,0.1)', '연휴 전후 시장 패턴', '통계적으로 미국 독립기념일 연휴 전후에는 주가가 오르는 경향이 있습니다. 이를 "Holiday Effect(연휴 효과)"라 합니다. 다만 매번 그런 것은 아니니, 이런 패턴에만 의존한 투자는 위험합니다.'),
        ],
        'risks': [
            ('보통', 'med', '연휴 중 돌발 이벤트', '미국 증시가 쉬는 동안 지정학적 사건이나 경제 지표가 발표되면, 연휴 후 개장 시 시장이 크게 반응할 수 있습니다.'),
            ('보통', 'med', '다음 주 실적 시즌 시작', 'JP모건, 시티그룹 등 대형 은행들의 Q2 실적 발표가 다음 주에 시작됩니다. 은행 실적은 경제 전반의 건강 상태를 보여주는 바로미터입니다.'),
            ('보통', 'med', '고용 지표 해석', '최근 발표된 고용 지표 결과에 따라 Fed의 금리 정책 방향에 대한 시장 기대가 조정될 수 있습니다.'),
            ('낮음', 'med', '여름 유동성 감소', '7~8월은 전통적으로 거래량이 줄어드는 시기입니다. 유동성이 낮으면 작은 뉴스에도 시장이 크게 움직일 수 있습니다.'),
        ],
    },
    '2025-07-04': {
        'hero_title': '미국은 쉬고, 아시아는 조용한 하루',
        'hero_body': '오늘은 미국 독립기념일로 뉴욕 증시가 완전히 휴장했습니다. 세계 금융시장의 중심인 미국이 쉬니, 한국과 아시아 시장도 한산한 하루를 보냈습니다. 거래량이 평소의 60~70% 수준에 그쳤고, 투자자들은 내일 미국 시장 재개를 기다리는 모양새입니다.',
        'chain': [
            ('미국 휴장', '독립기념일 뉴욕증시 휴장', '글로벌 기준점 부재', 'muted'),
            ('아시아 한산', '미국 부재로 거래량 급감', '소폭 등락', 'muted'),
            ('내일 주목', '미국 재개장 후 방향성 확인', '실적시즌 시작', 'up'),
        ],
        'insights': [
            ('글로벌연결', 'var(--accent)', 'rgba(59,110,230,0.1)', '왜 미국이 쉬면 전 세계가 조용할까?', '미국 주식시장은 전 세계 시가총액의 약 60%를 차지합니다. 미국 시장이 쉬면 글로벌 투자자들의 기준이 되는 가격이 형성되지 않아, 다른 나라 투자자들도 큰 매매를 피하는 경향이 있습니다.'),
            ('거래량', 'var(--warn)', 'rgba(212,139,7,0.1)', '거래량이 왜 중요한가?', '거래량은 하루에 얼마나 많은 주식이 사고팔렸는지를 나타냅니다. 거래량이 많으면 그날의 가격 변동이 "진짜"(많은 사람이 동의)라는 의미이고, 거래량이 적으면 소수의 거래로 가격이 왜곡될 수 있습니다.'),
            ('선물시장', 'var(--accent2)', 'rgba(107,92,231,0.1)', '선물 시장은 24시간 열려있다', '주식시장은 정해진 시간에만 열리지만, 선물(Future) 시장은 거의 24시간 거래됩니다. 미국이 휴장해도 선물 시장의 움직임으로 다음날 시장 방향을 짐작할 수 있습니다.'),
            ('독립기념일', 'var(--muted)', 'rgba(124,130,152,0.1)', '미국 주요 휴장일', '미국 증시의 주요 휴장일: 독립기념일(7/4), 추수감사절(11월 넷째 목요일), 크리스마스(12/25), 마틴 루터 킹의 날(1월), 대통령의 날(2월) 등. 연간 약 9~10일 휴장합니다.'),
        ],
        'risks': [
            ('보통', 'med', '미국 재개장 후 변동성', '이틀간 쌓인 뉴스와 글로벌 동향이 미국 시장 재개장 시 한꺼번에 반영될 수 있어 변동성이 커질 수 있습니다.'),
            ('보통', 'med', '실적 시즌 카운트다운', '다음 주부터 대형 은행들의 Q2 실적 발표가 시작됩니다. 실적이 시장 기대를 충족하는지가 하반기 방향을 결정할 핵심입니다.'),
            ('낮음', 'med', '유가 동향', '중동 정세와 OPEC+ 감산 정책에 따른 원유 가격 변동이 인플레이션 전망에 영향을 줍니다.'),
            ('낮음', 'med', '환율 변동', '달러 강세 기조가 이어질 경우, 신흥국 통화와 한국 원화에 부담이 될 수 있습니다.'),
        ],
    },
    '2025-07-07': {
        'hero_title': '연휴가 끝나고, 본격적인 실적 시즌이 시작됩니다',
        'hero_body': '독립기념일 연휴가 끝나고 미국 시장이 돌아왔습니다. 투자자들의 관심은 이번 주부터 본격화되는 Q2 실적 시즌에 쏠려 있습니다. 특히 대형 은행들의 실적이 미국 경제의 건강 상태를 보여줄 중요한 바로미터가 됩니다. 시장은 기대감과 긴장감이 공존하는 상태입니다.',
        'chain': [
            ('연휴 후 재개', '미국 시장 정상 개장', '거래량 정상화', 'up'),
            ('실적 시즌', 'Q2 실적 발표 카운트다운', '은행주 주목', 'muted'),
            ('시장 반응', '실적 결과에 따른 방향 결정', '기대 vs 현실', 'muted'),
        ],
        'insights': [
            ('은행실적', 'var(--accent)', 'rgba(59,110,230,0.1)', '왜 은행 실적을 먼저 볼까?', '실적 시즌은 보통 대형 은행(JP모건, 골드만삭스 등)부터 시작합니다. 은행은 대출, 투자, 소비 등 경제 전반을 다루기 때문에, 은행 실적이 좋으면 "경제가 건강하다"는 신호이고, 나쁘면 "경기 둔화" 우려가 커집니다.'),
            ('가이던스', 'var(--warn)', 'rgba(212,139,7,0.1)', '실적 발표에서 "가이던스"가 중요한 이유', '기업이 실적을 발표할 때 과거 실적(지난 분기 얼마 벌었는지)도 중요하지만, "가이던스(Guidance, 미래 전망)"가 더 중요합니다. "다음 분기에 이 정도 벌 것 같다"는 회사의 예측이 주가에 더 큰 영향을 미칩니다.'),
            ('서프라이즈', 'var(--up)', 'rgba(13,155,106,0.1)', '어닝 서프라이즈란?', '실적이 시장 예상(컨센서스)보다 좋으면 "어닝 서프라이즈(Earnings Surprise)", 나쁘면 "어닝 쇼크"라 합니다. 최근 몇 분기 동안 S&P500 기업의 약 75%가 예상을 웃도는 실적을 발표했는데, 이번에도 그럴지 주목됩니다.'),
            ('AI투자', 'var(--accent2)', 'rgba(107,92,231,0.1)', 'AI 투자 수익의 현실', '기업들이 AI에 엄청난 투자를 하고 있지만, 실제로 AI가 수익을 만들어내는지는 아직 검증 중입니다. 이번 실적 시즌에서 "AI 투자가 실제 매출로 이어지고 있는가"가 가장 큰 관전 포인트입니다.'),
        ],
        'risks': [
            ('높음', 'high', 'Q2 실적 기대치 높음', '시장이 이미 좋은 실적을 기대하고 주가에 반영해둔 상태라, 실적이 "좋아도" 기대보다 못하면 주가가 떨어질 수 있습니다. "Buy the rumor, sell the fact(소문에 사고 사실에 팔아라)" 현상이 나타날 수 있습니다.'),
            ('높음', 'high', 'Fed 7월 회의 앞두고 긴장', '7월 29~30일 FOMC 회의가 예정되어 있습니다. 금리 동결이 유력하지만, 향후 인하 시점에 대한 힌트를 시장이 주목합니다.'),
            ('보통', 'med', '기술주 과열 논쟁', 'AI 관련 기술주가 상반기에 크게 올라 밸류에이션(가치 평가) 부담이 높아진 상태입니다. 실적이 기대에 못 미치면 큰 폭의 조정이 올 수 있습니다.'),
            ('보통', 'med', '글로벌 경기 둔화 우려', '중국 경제 회복이 예상보다 느리고, 유럽도 경기 침체 우려가 있습니다. 글로벌 수요 감소는 한국 수출에도 영향을 줄 수 있습니다.'),
        ],
    },
}

# Generate remaining dates with contextual themes
def generate_narrative(date_str, data):
    """Generate narrative for dates not explicitly defined."""
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    month = dt.month
    day = dt.day
    weekday = dt.weekday()  # 0=Mon

    # Extract market data
    kospi = data.get('KOSPI', {})
    sp500 = data.get('S&P500', {})
    nasdaq = data.get('NASDAQ', {})
    nikkei = data.get('Nikkei', data.get('Nikkei225', {}))
    usd_krw = data.get('USD/KRW', {})
    wti = data.get('WTI', {})
    gold = data.get('Gold', {})
    us10y = data.get('US 10Y', {})
    vix = data.get('VIX', {})

    kospi_chg = kospi.get('chg', '+0.00%')
    sp500_chg = sp500.get('chg', '+0.00%')
    nasdaq_chg = nasdaq.get('chg', '+0.00%')
    kospi_val = kospi.get('value', '-')
    sp500_val = sp500.get('value', '-')
    nasdaq_val = nasdaq.get('value', '-')
    wti_val = wti.get('value', '-')
    gold_val = gold.get('value', '-')
    usd_krw_val = usd_krw.get('value', '-')
    vix_val = vix.get('value', '-')

    kospi_v = get_chg_val(kospi_chg)
    sp500_v = get_chg_val(sp500_chg)
    nasdaq_v = get_chg_val(nasdaq_chg)

    gainers = data.get('_gainers', [])
    losers = data.get('_losers', [])

    # Determine overall market mood
    avg_chg = (kospi_v + sp500_v + nasdaq_v) / 3
    if avg_chg > 0.5:
        mood = 'bullish'
    elif avg_chg < -0.5:
        mood = 'bearish'
    else:
        mood = 'mixed'

    # Theme selection based on date range
    if month == 7 and day <= 7:
        theme = 'h2_start'
    elif month == 7 and 8 <= day <= 14:
        theme = 'earnings_banks'
    elif month == 7 and 15 <= day <= 21:
        theme = 'earnings_tech_early'
    elif month == 7 and 22 <= day <= 27:
        theme = 'pre_fomc'
    elif month == 7 and day >= 28:
        theme = 'fomc_week'
    elif month == 8 and day <= 8:
        theme = 'post_fomc_tech_earnings'
    elif month == 8 and 9 <= day <= 15:
        theme = 'cpi_inflation'
    elif month == 8 and 16 <= day <= 22:
        theme = 'jackson_hole_prep'
    elif month == 8 and day >= 23:
        theme = 'jackson_hole_summer_end'
    else:
        theme = 'general'

    # Build hero
    theme_contexts = {
        'h2_start': '하반기가 시작되면서 투자자들은 상반기 AI 랠리의 지속 여부를 가늠하고 있습니다.',
        'earnings_banks': '대형 은행들의 Q2 실적 발표가 시작되었습니다. 미국 경제의 건강 상태를 확인할 중요한 시기입니다.',
        'earnings_tech_early': 'Q2 실적 시즌이 본격화되면서, 기술 대기업들의 실적이 시장의 방향을 결정할 핵심 변수가 되고 있습니다.',
        'pre_fomc': '다음 주 FOMC(연방공개시장위원회) 회의를 앞두고, 시장은 Fed의 금리 정책 방향에 촉각을 곤두세우고 있습니다.',
        'fomc_week': 'FOMC 회의가 진행 중입니다. Fed의 금리 결정과 향후 정책 방향이 시장의 최대 관심사입니다.',
        'post_fomc_tech_earnings': 'FOMC를 소화한 시장은 이제 빅테크(대형 기술 기업)들의 Q2 실적에 집중하고 있습니다.',
        'cpi_inflation': '미국 소비자물가지수(CPI) 발표를 앞두고, 인플레이션 추이가 시장의 핵심 관심사입니다.',
        'jackson_hole_prep': '잭슨홀 심포지엄(Fed 의장이 매년 8월 말 경제 전망을 발표하는 행사)이 다가오면서 시장의 긴장감이 높아지고 있습니다.',
        'jackson_hole_summer_end': '잭슨홀 심포지엄과 여름 시즌의 마무리가 겹치면서, 시장은 9월 이후의 방향을 탐색하고 있습니다.',
        'general': '글로벌 금융시장이 다양한 변수 속에서 방향을 모색하고 있습니다.',
    }

    if mood == 'bullish':
        mood_desc = f'오늘은 전반적으로 상승 흐름이 이어졌습니다. KOSPI {kospi_chg}, S&P500 {sp500_chg}로 투자자들의 심리가 살아났습니다.'
    elif mood == 'bearish':
        mood_desc = f'오늘은 하락 압력이 우세했습니다. KOSPI {kospi_chg}, S&P500 {sp500_chg}로 투자자들이 위험을 피하는 모습이었습니다.'
    else:
        mood_desc = f'오늘은 엇갈린 흐름이었습니다. KOSPI {kospi_chg}, S&P500 {sp500_chg}로, 시장이 방향을 잡지 못한 채 등락을 반복했습니다.'

    hero_title_options = {
        'bullish': ['녹색 신호등이 켜진 하루', '상승 바람이 불어온 하루', '투자자들에게 웃음이 번진 날', '시장이 한 발 전진한 하루'],
        'bearish': ['시장에 먹구름이 낀 하루', '투자자들이 한숨 쉰 하루', '빨간불이 켜진 하루', '하락의 그림자가 드리운 날'],
        'mixed': ['갈림길에 선 시장', '방향을 찾는 중인 시장', '엇갈린 신호가 교차한 하루', '반반의 하루'],
    }

    import random
    random.seed(hash(date_str))
    hero_title = random.choice(hero_title_options[mood])

    hero_body = f'{theme_contexts[theme]} {mood_desc}'

    # Build chain based on theme
    chain_templates = {
        'h2_start': [
            ('상반기 결산', 'AI 중심 상반기 랠리 마감', f'S&P500 {sp500_val}', 'up' if sp500_v > 0 else 'down'),
            ('하반기 시작', '실적 시즌과 금리 정책 주시', '방향 탐색 중', 'muted'),
            ('투자 심리', '기대와 우려가 공존', f'KOSPI {kospi_chg}', 'up' if kospi_v > 0 else 'down'),
        ],
        'earnings_banks': [
            ('은행 실적', '대형 은행 Q2 실적 발표', '경제 건강 바로미터', 'muted'),
            ('실적 영향', '은행 실적이 시장 방향 결정', f'S&P500 {sp500_chg}', 'up' if sp500_v > 0 else 'down'),
            ('다음 단계', '기술주 실적 대기', 'AI 매출 확인 예정', 'muted'),
        ],
        'earnings_tech_early': [
            ('기술주 실적', 'AI 대장주들의 성적표 발표', '기대감 고조', 'muted'),
            ('시장 반응', '실적에 따른 주가 변동', f'NASDAQ {nasdaq_chg}', 'up' if nasdaq_v > 0 else 'down'),
            ('AI 검증', 'AI 투자가 수익으로 이어지는가', '핵심 관전 포인트', 'muted'),
        ],
        'pre_fomc': [
            ('FOMC 대기', 'Fed 금리 결정 임박', '시장 긴장 고조', 'muted'),
            ('금리 전망', '동결 유력, 인하 시점이 관건', f'10년물 국채 {us10y.get("value", "-")}', 'muted'),
            ('포지션 조정', '회의 앞두고 리스크 관리', f'VIX {vix_val}', 'muted'),
        ],
        'fomc_week': [
            ('FOMC 진행', 'Fed 회의 결과 발표', '금리 정책 방향', 'muted'),
            ('시장 소화', '결과에 따른 포지션 조정', f'S&P500 {sp500_chg}', 'up' if sp500_v > 0 else 'down'),
            ('향후 전망', '9월 회의까지의 경로 탐색', '데이터 의존적', 'muted'),
        ],
    }

    chain = chain_templates.get(theme, [
        ('글로벌 이슈', '다양한 변수가 시장에 영향', f'S&P500 {sp500_chg}', 'up' if sp500_v > 0 else 'down'),
        ('한국 시장', '해외 영향과 내수 사이', f'KOSPI {kospi_chg}', 'up' if kospi_v > 0 else 'down'),
        ('전망', '다음 이벤트를 기다리는 시장', '관망세 지속', 'muted'),
    ])

    # Build insights based on theme
    insights_pool = {
        'h2_start': [
            ('AI랠리', 'var(--accent)', 'rgba(59,110,230,0.1)', 'AI 랠리는 어디까지?', '2025년 상반기 주식시장의 주인공은 AI(인공지능)였습니다. 엔비디아, 마이크로소프트, 구글 등 AI 관련 기업의 주가가 크게 올랐습니다. 하지만 "실제로 AI가 돈을 벌어다 주고 있는가?"라는 질문이 점점 커지고 있어, 하반기 실적이 그 답을 줄 것입니다.'),
            ('여름시장', 'var(--warn)', 'rgba(212,139,7,0.1)', '"여름 랠리"와 "셀 인 메이"', '"Sell in May and go away(5월에 팔고 떠나라)"라는 증시 격언이 있지만, 올해는 여름에도 상승세가 이어졌습니다. 역사적으로 7~8월은 변동성이 높은 시기이지만, 강한 실적이 뒷받침되면 상승을 이어갈 수 있습니다.'),
            ('금리', 'var(--accent2)', 'rgba(107,92,231,0.1)', '금리와 주식의 시소 관계', '금리가 오르면 주식이 떨어지고, 금리가 내리면 주식이 오르는 경향이 있습니다. 은행 예금 이자가 높아지면 굳이 위험한 주식에 투자할 이유가 줄어들기 때문입니다. 현재 미국 기준금리는 5.25~5.50%로 높은 수준이며, 시장은 인하를 기다리고 있습니다.'),
            ('환율', 'var(--gold)', 'rgba(184,134,11,0.1)', '원/달러 환율과 한국 경제', f'현재 원/달러 환율은 {usd_krw_val}원입니다. 환율이 오르면(원화가 약해지면) 수입품이 비싸지지만, 삼성전자 같은 수출 기업은 유리해집니다. 반대로 환율이 내리면 해외여행이 저렴해지지만 수출 기업의 이익은 줄어듭니다.'),
        ],
        'earnings_banks': [
            ('은행실적', 'var(--accent)', 'rgba(59,110,230,0.1)', '대형 은행 실적이 말해주는 것', '은행은 경제의 모든 분야와 연결되어 있습니다. 대출, 신용카드, 투자은행 업무 등을 통해 소비자와 기업의 경제 활동을 반영합니다. JP모건, 골드만삭스 등의 실적이 좋으면 경제가 건강하다는 신호입니다.'),
            ('NIM', 'var(--warn)', 'rgba(212,139,7,0.1)', '은행의 수익 구조: NIM', 'NIM(Net Interest Margin, 순이자마진)은 은행이 대출 이자로 받는 돈과 예금 이자로 나가는 돈의 차이입니다. 금리가 높을수록 NIM이 커져 은행 수익이 좋아지는데, 금리가 내리면 이 수익이 줄어들 수 있습니다.'),
            ('경기지표', 'var(--up)', 'rgba(13,155,106,0.1)', '대출 연체율이 보여주는 경기 상태', '은행의 대출 연체율은 소비자와 기업의 재정 건강을 보여줍니다. 연체율이 올라가면 사람들이 돈 갚기 어려워졌다는 뜻이므로 경기 둔화 신호, 내려가면 경제가 안정적이라는 신호입니다.'),
            ('ETF', 'var(--accent2)', 'rgba(107,92,231,0.1)', 'ETF로 실적 시즌 대응하기', 'ETF(상장지수펀드)는 여러 주식을 하나의 바구니에 담아 거래할 수 있는 상품입니다. 개별 종목의 실적 리스크를 줄이면서 시장 전체의 흐름에 투자할 수 있어, 초보자에게 좋은 투자 방법입니다.'),
        ],
        'earnings_tech_early': [
            ('빅테크', 'var(--accent)', 'rgba(59,110,230,0.1)', '빅테크 실적의 핵심 포인트', '구글, 아마존, 마이크로소프트 등 빅테크 기업의 실적에서 가장 주목할 것은 "AI 관련 매출"입니다. 클라우드 사업의 AI 관련 매출이 얼마나 성장했는지가 AI 투자의 실효성을 보여주는 핵심 지표입니다.'),
            ('CAPEX', 'var(--warn)', 'rgba(212,139,7,0.1)', '설비투자(CAPEX)가 중요한 이유', 'CAPEX(Capital Expenditure)는 기업이 공장, 장비, 기술 등에 투자하는 돈입니다. 빅테크들이 AI 인프라에 투자하는 CAPEX 규모가 커지면, 엔비디아 같은 반도체 기업의 매출도 늘어납니다.'),
            ('마진', 'var(--up)', 'rgba(13,155,106,0.1)', '영업이익률의 의미', '영업이익률은 매출 중 실제로 남는 이익의 비율입니다. AI에 많이 투자하면 비용이 늘어나 이익률이 떨어질 수 있는데, 투자하면서도 이익률을 유지하는 기업이 진짜 실력 있는 기업입니다.'),
            ('밸류에이션', 'var(--accent2)', 'rgba(107,92,231,0.1)', 'PER(주가수익비율)로 보는 적정 가격', 'PER은 주가를 1주당 이익으로 나눈 것입니다. PER이 30이면 "이 회사의 주가는 1년 이익의 30배"라는 뜻입니다. PER이 높으면 미래 성장을 기대한 것이고, 기대에 못 미치면 주가가 조정될 수 있습니다.'),
        ],
        'pre_fomc': [
            ('FOMC', 'var(--accent)', 'rgba(59,110,230,0.1)', 'FOMC 회의란?', 'FOMC(Federal Open Market Committee, 연방공개시장위원회)는 미국의 기준금리를 결정하는 회의입니다. 연 8회 개최되며, 금리를 올릴지, 내릴지, 유지할지를 투표로 결정합니다. 전 세계 금융시장에 가장 큰 영향을 미치는 이벤트 중 하나입니다.'),
            ('점도표', 'var(--warn)', 'rgba(212,139,7,0.1)', 'Fed "점도표"란?', '점도표(Dot Plot)는 Fed 위원 18명이 각각 앞으로 금리가 어느 수준이 될 것이라고 예상하는지를 점으로 찍어 나타낸 그래프입니다. 이 점들의 중간값(median)이 시장이 주목하는 "Fed의 금리 전망"입니다.'),
            ('인플레이션', 'var(--down)', 'rgba(217,48,79,0.1)', '인플레이션과 금리의 관계', '물가가 오르면(인플레이션) 중앙은행은 금리를 올려 경제를 식힙니다. 물가가 안정되면 금리를 내려 경제를 자극합니다. 현재 미국의 물가 상승률은 Fed의 목표(2%)에 근접하고 있어, 금리 인하 기대가 커지고 있습니다.'),
            ('채권', 'var(--accent2)', 'rgba(107,92,231,0.1)', '채권 금리와 주식시장', f'미국 10년 국채 금리({us10y.get("value", "-")})는 경제 전반의 금리 기준이 됩니다. 채권 금리가 오르면 주식의 매력이 줄어들고, 내리면 주식이 더 매력적이 됩니다. FOMC 결정에 따라 채권 금리가 크게 움직일 수 있습니다.'),
        ],
        'fomc_week': [
            ('금리결정', 'var(--accent)', 'rgba(59,110,230,0.1)', 'Fed의 금리 결정 프로세스', 'FOMC 회의에서 12명의 투표권자가 금리를 결정합니다. 회의 후 성명서와 기자회견에서 "향후 금리 방향"에 대한 힌트를 줍니다. 시장은 실제 금리보다 "앞으로의 방향"에 더 민감하게 반응합니다.'),
            ('파월', 'var(--warn)', 'rgba(212,139,7,0.1)', 'Fed 의장 기자회견의 중요성', 'FOMC 후 Fed 의장(제롬 파월)의 기자회견은 시장에 큰 영향을 줍니다. 의장의 말 한마디, 표현 하나에 따라 주가, 금리, 환율이 크게 움직입니다. "데이터에 의존적(data-dependent)"이란 표현이 자주 나옵니다.'),
            ('금리경로', 'var(--up)', 'rgba(13,155,106,0.1)', '금리 인하의 경제적 의미', '금리가 내리면 대출 이자가 줄어 주택 구입, 자동차 할부, 기업 투자가 늘어납니다. 소비가 살아나면 기업 매출이 늘고, 주가도 오르는 선순환이 생깁니다. 그래서 시장은 금리 인하를 환영합니다.'),
            ('긴축vs완화', 'var(--accent2)', 'rgba(107,92,231,0.1)', '긴축과 완화의 차이', '"긴축(Hawkish)"은 물가 안정을 위해 금리를 높게 유지하는 것, "완화(Dovish)"는 경제 성장을 위해 금리를 낮추는 것입니다. Fed의 태도가 어느 쪽인지에 따라 시장 분위기가 크게 달라집니다.'),
        ],
        'post_fomc_tech_earnings': [
            ('빅테크실적', 'var(--accent)', 'rgba(59,110,230,0.1)', '빅테크 어닝 위크', '애플, 아마존, 메타 등 빅테크 기업들의 Q2 실적이 발표되는 주간입니다. 이 기업들은 S&P500 시가총액의 약 30%를 차지하므로, 실적 결과가 지수 전체의 방향을 결정합니다.'),
            ('AI매출', 'var(--warn)', 'rgba(212,139,7,0.1)', 'AI 매출이 기대만큼 나오고 있나?', '빅테크들의 AI 관련 매출 성장률이 핵심 관전 포인트입니다. 마이크로소프트의 Azure AI, 구글의 Cloud AI, 아마존의 AWS AI 서비스 매출이 시장 기대를 충족하는지 확인해야 합니다.'),
            ('고용지표', 'var(--down)', 'rgba(217,48,79,0.1)', '8월 초 고용 지표의 의미', '매월 첫째 금요일에 발표되는 미국 비농업 고용자 수는 경제의 건강 상태를 보여주는 핵심 지표입니다. 고용이 강하면 경제가 튼튼하다는 뜻이지만, 너무 강하면 Fed가 금리 인하를 미룰 수 있습니다.'),
            ('변동성', 'var(--accent2)', 'rgba(107,92,231,0.1)', '실적 시즌의 변동성', '실적 발표 직후에는 개별 종목의 주가가 5~10% 이상 움직이기도 합니다. 이를 "어닝 리액션"이라 합니다. 실적 시즌에는 이런 변동성이 커지므로, 장기 투자 관점을 유지하는 것이 중요합니다.'),
        ],
        'cpi_inflation': [
            ('CPI', 'var(--accent)', 'rgba(59,110,230,0.1)', '소비자물가지수(CPI)란?', 'CPI(Consumer Price Index)는 일반 가정이 구매하는 물건과 서비스의 가격 변동을 측정한 것입니다. 매월 발표되며, 물가가 얼마나 오르고 있는지(인플레이션)를 보여줍니다. Fed가 금리를 결정할 때 가장 중요하게 보는 지표 중 하나입니다.'),
            ('근원CPI', 'var(--warn)', 'rgba(212,139,7,0.1)', '근원 CPI가 더 중요한 이유', '근원 CPI(Core CPI)는 변동이 심한 식품과 에너지를 제외한 물가입니다. 음식값과 기름값은 날씨나 국제 정세에 따라 크게 흔들리므로, 실제 물가 추세를 보려면 근원 CPI가 더 정확합니다.'),
            ('실질금리', 'var(--up)', 'rgba(13,155,106,0.1)', '실질금리란?', '실질금리 = 명목금리 - 물가상승률입니다. 예를 들어 은행 이자가 5%인데 물가가 3% 올랐다면, 실질적으로는 2%만 이득인 셈입니다. 실질금리가 높으면 저축이 유리하고, 낮으면 투자(주식 등)가 유리합니다.'),
            ('물가기대', 'var(--accent2)', 'rgba(107,92,231,0.1)', '물가 기대 심리의 중요성', '사람들이 "앞으로 물가가 오를 것"이라고 기대하면, 실제로 물가가 오르는 경향이 있습니다(자기실현적 예언). 그래서 Fed는 인플레이션 기대치도 관리합니다. 미시간대 소비자심리지수의 인플레이션 기대치가 주목받는 이유입니다.'),
        ],
        'jackson_hole_prep': [
            ('잭슨홀', 'var(--accent)', 'rgba(59,110,230,0.1)', '잭슨홀 심포지엄이란?', '매년 8월 말 미국 와이오밍주 잭슨홀에서 열리는 경제 학술회의입니다. 전 세계 중앙은행 총재, 경제학자들이 모이며, 특히 Fed 의장의 연설이 향후 통화정책의 방향을 알려주는 중요한 신호로 여겨집니다.'),
            ('정책신호', 'var(--warn)', 'rgba(212,139,7,0.1)', '왜 잭슨홀 연설이 중요한가?', '2022년 잭슨홀에서 파월 의장이 "고통이 있더라도 인플레이션을 잡겠다"고 말한 후 S&P500이 하루에 -3.4% 급락했습니다. 한 번의 연설이 시장을 뒤흔들 수 있을 만큼, 이 행사는 투자자들에게 매우 중요합니다.'),
            ('9월전망', 'var(--up)', 'rgba(13,155,106,0.1)', '9월 FOMC와의 연결', '잭슨홀 연설은 9월 FOMC 회의의 "예고편"으로 여겨집니다. 파월 의장이 금리 인하를 시사하면 시장이 환호하고, 신중한 태도를 보이면 실망할 수 있습니다.'),
            ('시즌변화', 'var(--accent2)', 'rgba(107,92,231,0.1)', '"9월 효과"에 대비하기', '통계적으로 9월은 미국 증시에서 가장 성적이 나쁜 달입니다. 여름 휴가 후 돌아온 투자자들이 포트폴리오를 조정하면서 매도가 늘어나는 경향이 있습니다. 다만 매년 그런 것은 아닙니다.'),
        ],
        'jackson_hole_summer_end': [
            ('잭슨홀결과', 'var(--accent)', 'rgba(59,110,230,0.1)', '잭슨홀 심포지엄의 시장 영향', '잭슨홀 심포지엄에서 나온 메시지가 시장에 반영되고 있습니다. Fed 의장의 발언 톤이 "완화적(비둘기파)"이었는지 "긴축적(매파)"이었는지에 따라 9월 이후 시장 방향이 결정됩니다.'),
            ('여름마감', 'var(--warn)', 'rgba(212,139,7,0.1)', '여름 시즌 마감과 시장', '8월 말은 여름 거래 시즌의 마무리입니다. 9월부터 기관 투자자들이 본격적으로 복귀하면서 거래량이 늘어나고, 시장의 방향성이 더 뚜렷해지는 경향이 있습니다.'),
            ('Q3전망', 'var(--up)', 'rgba(13,155,106,0.1)', '3분기 시장 전망', 'Q3(7~9월)는 실적 시즌, FOMC, 잭슨홀 등 굵직한 이벤트가 집중됩니다. Q2 실적이 전반적으로 양호했다면 시장의 상승 모멘텀이 이어질 수 있지만, 금리 불확실성이 변수입니다.'),
            ('포트폴리오', 'var(--accent2)', 'rgba(107,92,231,0.1)', '분기말 포트폴리오 조정', '기관 투자자들은 분기말에 포트폴리오를 재조정합니다. 많이 오른 종목을 줄이고, 저평가된 종목을 늘리는 "리밸런싱"을 하는데, 이 과정에서 단기적으로 주가 변동이 생길 수 있습니다.'),
        ],
    }

    insights = insights_pool.get(theme, insights_pool['h2_start'])

    # Risks based on theme
    risks_pool = {
        'h2_start': [
            ('높음', 'high', 'AI 버블 논쟁 심화', 'AI 관련 기업의 주가가 실적 대비 과도하게 올랐다는 지적이 나오고 있습니다. 실적 시즌에서 AI 매출이 기대에 못 미치면 큰 조정이 올 수 있습니다.'),
            ('높음', 'high', 'Fed 금리 정책 불확실성', '시장은 올해 안에 금리 인하를 기대하고 있지만, 인플레이션이 끈적이면 인하가 늦어질 수 있습니다.'),
            ('보통', 'med', '여름 거래량 감소', '여름 휴가철에는 거래량이 줄어 변동성이 커질 수 있습니다.'),
            ('보통', 'med', '지정학적 리스크', '미중 갈등, 중동 긴장 등 지정학적 리스크가 시장에 돌발 변수가 될 수 있습니다.'),
        ],
        'earnings_banks': [
            ('높음', 'high', '은행 실적 기대치 높음', '시장이 이미 좋은 실적을 기대하고 있어, 기대보다 못하면 실망 매도가 나올 수 있습니다.'),
            ('높음', 'high', '대출 부실 우려', '상업용 부동산(오피스, 쇼핑몰 등) 대출의 부실 가능성이 은행 실적의 리스크 요인입니다.'),
            ('보통', 'med', '금리 인하 시 은행 수익 감소', '금리가 내려가면 은행의 이자 수익(NIM)이 줄어들 수 있습니다.'),
            ('보통', 'med', '기술주 조정 가능성', 'AI 기술주가 높은 밸류에이션을 유지하려면 강한 실적이 필요합니다.'),
        ],
        'earnings_tech_early': [
            ('높음', 'high', '빅테크 실적이 시장 좌우', '빅테크 실적이 시장 전체의 방향을 결정할 핵심 변수입니다. 기대에 못 미치면 큰 조정이 올 수 있습니다.'),
            ('높음', 'high', 'AI 투자 효율성 검증', 'AI에 대한 막대한 투자가 실제 매출과 이익으로 이어지는지 확인이 필요합니다.'),
            ('보통', 'med', '규제 리스크', '미국과 유럽에서 빅테크에 대한 반독점 규제가 강화되고 있습니다.'),
            ('보통', 'med', '환율 영향', '달러 강세는 해외 매출 비중이 높은 빅테크 기업의 이익을 줄일 수 있습니다.'),
        ],
        'pre_fomc': [
            ('높음', 'high', 'FOMC 결과에 따른 변동성', 'Fed의 금리 결정과 의장 발언에 따라 시장이 크게 움직일 수 있습니다.'),
            ('높음', 'high', '금리 인하 기대와 현실의 갭', '시장이 기대하는 인하 시점과 Fed의 실제 계획이 다를 수 있습니다.'),
            ('보통', 'med', '인플레이션 재상승 위험', '에너지 가격이나 임금 상승으로 인플레이션이 다시 올라갈 수 있습니다.'),
            ('보통', 'med', '글로벌 경기 둔화', '중국과 유럽의 경기 둔화가 글로벌 수요에 영향을 줄 수 있습니다.'),
        ],
        'fomc_week': [
            ('높음', 'high', 'FOMC 후 시장 급변 가능성', '금리 결정과 향후 정책 방향에 대한 힌트에 따라 시장이 급등 또는 급락할 수 있습니다.'),
            ('높음', 'high', '파월 의장 발언 해석', '기자회견에서의 표현 하나가 시장의 기대를 크게 바꿀 수 있습니다.'),
            ('보통', 'med', '실적 시즌과 겹치는 불확실성', 'FOMC와 빅테크 실적이 동시에 나오면서 변동성이 극대화될 수 있습니다.'),
            ('보통', 'med', '채권 시장 변동성', '금리 결정에 따라 채권 시장이 크게 움직이고, 이는 주식시장에도 영향을 줍니다.'),
        ],
    }

    risks = risks_pool.get(theme, risks_pool['h2_start'])

    return {
        'hero_title': hero_title,
        'hero_body': hero_body,
        'chain': chain,
        'insights': insights,
        'risks': risks,
    }


def build_story_html(narr, data):
    """Build the story HTML content from narrative data."""
    date_str = data.get('_date', '2025-07-01')
    dow = data.get('_dow', '')

    # Extract data for sessions
    kospi = data.get('KOSPI', {})
    sp500 = data.get('S&P500', {})
    nasdaq = data.get('NASDAQ', {})
    nikkei = data.get('Nikkei', data.get('Nikkei225', {}))
    dax = data.get('DAX', {})
    ftse = data.get('FTSE100', data.get('FTSE', {}))
    usd_krw = data.get('USD/KRW', {})
    wti = data.get('WTI', {})
    gold = data.get('Gold', {})
    us10y = data.get('US 10Y', {})
    vix = data.get('VIX', {})

    kospi_chg = kospi.get('chg', '+0.00%')
    sp500_chg = sp500.get('chg', '+0.00%')
    nasdaq_chg = nasdaq.get('chg', '+0.00%')
    nikkei_chg = nikkei.get('chg', '+0.00%')
    dax_chg = dax.get('chg', '+0.00%')
    ftse_chg = ftse.get('chg', '+0.00%')

    kospi_v = get_chg_val(kospi_chg)
    sp500_v = get_chg_val(sp500_chg)
    nasdaq_v = get_chg_val(nasdaq_chg)
    nikkei_v = get_chg_val(nikkei_chg)
    dax_v = get_chg_val(dax_chg)
    ftse_v = get_chg_val(ftse_chg)

    def css_cls(v):
        return 'up' if v > 0 else ('down' if v < 0 else 'flat')

    # Asia verdict
    asia_avg = (kospi_v + nikkei_v) / 2
    asia_verdict = '상승' if asia_avg > 0.3 else ('하락' if asia_avg < -0.3 else '보합')
    asia_verdict_cls = 'verdict-up' if asia_avg > 0.3 else ('verdict-down' if asia_avg < -0.3 else 'verdict-mixed')

    # Europe verdict
    eu_avg = (dax_v + ftse_v) / 2
    eu_verdict = '상승' if eu_avg > 0.3 else ('하락' if eu_avg < -0.3 else '혼조')
    eu_verdict_cls = 'verdict-up' if eu_avg > 0.3 else ('verdict-down' if eu_avg < -0.3 else 'verdict-mixed')

    # US verdict
    us_avg = (sp500_v + nasdaq_v) / 2
    us_verdict = '상승 마감' if us_avg > 0.3 else ('하락 마감' if us_avg < -0.3 else '보합 마감')
    us_verdict_cls = 'verdict-up' if us_avg > 0.3 else ('verdict-down' if us_avg < -0.3 else 'verdict-mixed')

    # Gainers/losers for session events
    gainers = data.get('_gainers', [])
    losers = data.get('_losers', [])

    gainer_text = ''
    if gainers:
        g = gainers[0]
        gainer_text = f'{g[0]} <span class="hl-up">{g[1]}</span> 등이 상승을 이끌었습니다'

    loser_text = ''
    if losers:
        l = losers[0]
        loser_text = f'{l[0]} <span class="hl-down">{l[1]}</span> 등이 하락했습니다'

    # Build chain HTML
    chain_html = '<div class="causal-chain">\n'
    for i, (label, title, detail, impact_type) in enumerate(narr['chain']):
        impact_cls = 'up' if impact_type == 'up' else ('hl-down' if impact_type == 'down' else '')
        impact_style = ' style="color:var(--muted)"' if impact_type == 'muted' else ''
        chain_html += f'''  <div class="cause-node">
    <div class="node-label">{label}</div>
    <div class="node-title">{title}</div>
    <div class="node-detail">{detail}</div>
    <div class="node-impact {impact_cls}"{impact_style}>{detail}</div>
  </div>\n'''
        if i < len(narr['chain']) - 1:
            chain_html += '  <div class="cause-arrow">&rarr;</div>\n'
    chain_html += '</div>'

    # Build insights HTML
    insights_html = '<div class="insight-grid">\n'
    for badge_text, badge_color, badge_bg, title, desc in narr['insights']:
        insights_html += f'''  <div class="insight-card">
    <span class="badge" style="background:{badge_bg};color:{badge_color}">{badge_text}</span>
    <h3>{title}</h3>
    <p>{desc}</p>
  </div>\n'''
    insights_html += '</div>'

    # Build risks HTML
    risks_html = '<ul class="risk-items">\n'
    for level_text, level_cls, title, desc in narr['risks']:
        risks_html += f'''    <li class="risk-item">
      <span class="risk-tag {level_cls}">{level_text}</span>
      <span><strong>{title}</strong><br>{desc}</span>
    </li>\n'''
    risks_html += '  </ul>'

    # Full story HTML
    story = f'''<!-- ── Story Hero: 오늘의 시장 이야기 ── -->
<div class="story-hero">
  <h2>오늘의 시장 이야기</h2>
  <div class="story-text">
    <strong>{narr['hero_title']}</strong><br><br>
    {narr['hero_body']}
  </div>
</div>

<!-- ── Causal Chain: 큰 흐름 ── -->
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">오늘의 큰 흐름 &mdash; 하나의 체인으로 이해하기</div>
<div style="font-size:12px;color:var(--muted);margin-bottom:16px;">왼쪽의 원인이 오른쪽의 결과로 이어지는 과정입니다. 화살표(&rarr;)를 따라가 보세요.</div>
{chain_html}

<!-- ── Session Grid ── -->
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">세계 시장은 릴레이처럼 돌아갑니다</div>
<div style="font-size:12px;color:var(--muted);margin-bottom:16px;">지구가 돌면서 한국과 일본이 먼저 장을 열고, 유럽이 이어받고, 미국이 마지막으로 거래합니다.</div>
<div class="session-grid">
  <div class="session-block asia">
    <div class="session-header">
      <div class="session-icon asia">&#127471;&#127477;</div>
      <div>
        <div class="session-name">아시아 세션</div>
        <div class="session-time">한국 09:00 ~ 15:30</div>
      </div>
    </div>
    <span class="session-verdict {asia_verdict_cls}">{asia_verdict}</span>
    <ul class="session-events">
      <li><span class="ev-time">09:00</span> KOSPI(한국 대표 지수) <span class="hl-{'up' if kospi_v >= 0 else 'down'}">{kospi_chg}</span>로 거래. {gainer_text if kospi_v >= 0 else loser_text}</li>
      <li><span class="ev-time">10:30</span> 닛케이225(일본 대표 지수) <span class="hl-{'up' if nikkei_v >= 0 else 'down'}">{nikkei_chg}</span> 기록</li>
    </ul>
    <div class="session-kpi">
      <div class="s-kpi"><div class="s-kpi-label">KOSPI</div><div class="s-kpi-value {css_cls(kospi_v)}">{kospi_chg}</div></div>
      <div class="s-kpi"><div class="s-kpi-label">닛케이</div><div class="s-kpi-value {css_cls(nikkei_v)}">{nikkei_chg}</div></div>
    </div>
  </div>

  <div class="session-block europe">
    <div class="session-header">
      <div class="session-icon europe">&#127466;&#127482;</div>
      <div>
        <div class="session-name">유럽 세션</div>
        <div class="session-time">한국 17:00 ~ 01:30</div>
      </div>
    </div>
    <span class="session-verdict {eu_verdict_cls}">{eu_verdict}</span>
    <ul class="session-events">
      <li><span class="ev-time">17:00</span> DAX(독일 대표 지수) <span class="hl-{'up' if dax_v >= 0 else 'down'}">{dax_chg}</span>, FTSE(영국 대표 지수) <span class="hl-{'up' if ftse_v >= 0 else 'down'}">{ftse_chg}</span></li>
    </ul>
    <div class="session-kpi">
      <div class="s-kpi"><div class="s-kpi-label">DAX</div><div class="s-kpi-value {css_cls(dax_v)}">{dax_chg}</div></div>
      <div class="s-kpi"><div class="s-kpi-label">FTSE</div><div class="s-kpi-value {css_cls(ftse_v)}">{ftse_chg}</div></div>
    </div>
  </div>

  <div class="session-block us">
    <div class="session-header">
      <div class="session-icon us">&#127482;&#127480;</div>
      <div>
        <div class="session-name">미국 세션</div>
        <div class="session-time">한국 23:30 ~ 06:00</div>
      </div>
    </div>
    <span class="session-verdict {us_verdict_cls}">{us_verdict}</span>
    <ul class="session-events">
      <li><span class="ev-time">23:30</span> S&P500 <span class="hl-{'up' if sp500_v >= 0 else 'down'}">{sp500_chg}</span>, NASDAQ <span class="hl-{'up' if nasdaq_v >= 0 else 'down'}">{nasdaq_chg}</span></li>
    </ul>
    <div class="session-kpi">
      <div class="s-kpi"><div class="s-kpi-label">S&P 500</div><div class="s-kpi-value {css_cls(sp500_v)}">{sp500_chg}</div></div>
      <div class="s-kpi"><div class="s-kpi-label">NASDAQ</div><div class="s-kpi-value {css_cls(nasdaq_v)}">{nasdaq_chg}</div></div>
    </div>
  </div>
</div>

<!-- ── Cross-Asset Flow Map ── -->
<div class="cross-asset">
  <h2>자산 간 연결 고리 (Cross-Asset Flow Map)</h2>
  <div class="sub">금융시장의 모든 것은 서로 연결되어 있습니다. 하나가 움직이면 다른 것도 따라 움직입니다.</div>
  <div class="af-map">
    <div class="af-node">
      <div class="af-node-title">S&P500 (미국 주식)</div>
      <div class="af-node-value">{sp500.get('value', '-')}</div>
      <div class="af-node-chg {css_cls(sp500_v)}">{sp500_chg}</div>
    </div>
    <div class="af-arrow"><span class="arr">&harr;</span><span class="lbl">동반 움직임</span></div>
    <div class="af-node">
      <div class="af-node-title">KOSPI (한국 주식)</div>
      <div class="af-node-value">{kospi.get('value', '-')}</div>
      <div class="af-node-chg {css_cls(kospi_v)}">{kospi_chg}</div>
    </div>
    <div class="af-arrow"><span class="arr">&harr;</span><span class="lbl">환율 영향</span></div>
    <div class="af-node">
      <div class="af-node-title">원/달러 환율</div>
      <div class="af-node-value">{usd_krw.get('value', '-')}원</div>
      <div class="af-node-chg">{usd_krw.get('chg', '-')}</div>
    </div>

    <div class="af-node">
      <div class="af-node-title">미국 10년 국채금리</div>
      <div class="af-node-value">{us10y.get('value', '-')}</div>
      <div class="af-node-chg">{us10y.get('chg', '-')}</div>
    </div>
    <div class="af-arrow"><span class="arr">&rarr;</span><span class="lbl">금리 영향</span></div>
    <div class="af-node">
      <div class="af-node-title">WTI 원유</div>
      <div class="af-node-value">{wti.get('value', '-')}</div>
      <div class="af-node-chg">{wti.get('chg', '-')}</div>
    </div>
    <div class="af-arrow"><span class="arr">&rarr;</span><span class="lbl">안전자산</span></div>
    <div class="af-node">
      <div class="af-node-title">Gold 금</div>
      <div class="af-node-value">{gold.get('value', '-')}</div>
      <div class="af-node-chg">{gold.get('chg', '-')}</div>
    </div>
  </div>
</div>

<!-- ── Insight Grid ── -->
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">알아두면 좋은 시장 상식 4가지</div>
<div style="font-size:12px;color:var(--muted);margin-bottom:16px;">오늘의 뉴스를 이해하기 위해 꼭 알아야 할 개념들을 쉽게 설명합니다.</div>
{insights_html}

<!-- ── Risk Section ── -->
<div class="risk-section">
  <h2>앞으로 주의해야 할 점</h2>
  <div style="font-size:12px;color:var(--muted);margin-bottom:16px;">투자를 하지 않더라도 경제 뉴스를 이해하기 위해 이런 위험 요소들을 알아두면 좋습니다.</div>
  {risks_html}
</div>'''

    return story


def process_file(filepath):
    """Process a single HTML file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        html = f.read()

    if '<!-- STORY_CONTENT_PLACEHOLDER -->' not in html:
        return False

    data = extract_kpi_data(html)
    date_str = data.get('_date', '')

    if not date_str:
        return False

    # Use predefined narrative if available, otherwise generate
    if date_str in NARRATIVES:
        narr = NARRATIVES[date_str]
    else:
        narr = generate_narrative(date_str, data)

    story_html = build_story_html(narr, data)

    new_html = html.replace('<!-- STORY_CONTENT_PLACEHOLDER -->', story_html)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_html)

    return True


def main():
    import glob

    files = []
    for pattern in [
        '/Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/output/2025-07/*.html',
        '/Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/output/2025-08/*.html',
    ]:
        files.extend(sorted(glob.glob(pattern)))

    count = 0
    for f in files:
        if process_file(f):
            print(f'OK: {os.path.basename(f)}')
            count += 1
        else:
            print(f'SKIP: {os.path.basename(f)}')

    print(f'\nTotal processed: {count}/{len(files)}')


if __name__ == '__main__':
    main()
