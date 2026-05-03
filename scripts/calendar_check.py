"""날짜-요일 검증 유틸리티.

사용법:
    python scripts/calendar_check.py 2026-05-04          # 해당 주 캘린더
    python scripts/calendar_check.py 2026-05-04 --month  # 해당 월 전체
    python scripts/calendar_check.py 2026-05-04 --week W18  # 특정 주차
"""
import argparse
from datetime import date, timedelta

try:
    import holidays
    KR_HOLIDAYS = holidays.KR()
except ImportError:
    KR_HOLIDAYS = {}

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]
WEEKDAY_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def is_business_day(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    if d in KR_HOLIDAYS:
        return False
    return True


def get_week_dates(d: date) -> list[date]:
    """d가 속한 주의 월~일 반환."""
    monday = d - timedelta(days=d.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def get_month_dates(d: date) -> list[date]:
    """d가 속한 월의 모든 날짜 반환."""
    first = d.replace(day=1)
    dates = []
    current = first
    while current.month == first.month:
        dates.append(current)
        current += timedelta(days=1)
    return dates


def get_iso_week_dates(year: int, week: int) -> list[date]:
    """ISO 주차의 월~일 반환."""
    jan4 = date(year, 1, 4)
    start_of_w1 = jan4 - timedelta(days=jan4.weekday())
    monday = start_of_w1 + timedelta(weeks=week - 1)
    return [monday + timedelta(days=i) for i in range(7)]


def get_business_days_in_week(d: date) -> list[date]:
    """d가 속한 주의 영업일만 반환."""
    return [day for day in get_week_dates(d) if is_business_day(day)]


def format_calendar(dates: list[date], title: str = "") -> str:
    lines = []
    if title:
        lines.append(f"{'='*50}")
        lines.append(f"  {title}")
        lines.append(f"{'='*50}")

    lines.append(f"{'날짜':<12} {'요일':<4} {'EN':<5} {'영업일':<6} {'비고'}")
    lines.append("-" * 50)

    for d in dates:
        wd_kr = WEEKDAY_KR[d.weekday()]
        wd_en = WEEKDAY_EN[d.weekday()]
        biz = "✓" if is_business_day(d) else "✗"
        note = ""
        if d.weekday() >= 5:
            note = "주말"
        elif d in KR_HOLIDAYS:
            note = f"공휴일({KR_HOLIDAYS.get(d, '')})"
        lines.append(f"{d.isoformat():<12} {wd_kr:<4} {wd_en:<5} {biz:<6} {note}")

    biz_days = [d for d in dates if is_business_day(d)]
    lines.append("-" * 50)
    lines.append(f"영업일 수: {len(biz_days)}일")
    if biz_days:
        lines.append(f"영업일 범위: {biz_days[0].isoformat()} ~ {biz_days[-1].isoformat()}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="날짜-요일 검증 캘린더")
    parser.add_argument("date", help="기준 날짜 (YYYY-MM-DD)")
    parser.add_argument("--month", action="store_true", help="월 전체 표시")
    parser.add_argument("--week", type=str, help="ISO 주차 (예: W18)")
    args = parser.parse_args()

    ref = date.fromisoformat(args.date)

    if args.week:
        week_num = int(args.week.upper().replace("W", ""))
        dates = get_iso_week_dates(ref.year, week_num)
        title = f"{ref.year}년 W{week_num:02d} 캘린더"
    elif args.month:
        dates = get_month_dates(ref)
        title = f"{ref.year}년 {ref.month}월 캘린더"
    else:
        dates = get_week_dates(ref)
        iso_year, iso_week, _ = ref.isocalendar()
        title = f"{ref.isoformat()} 포함 주 (W{iso_week:02d}) 캘린더"

    print(format_calendar(dates, title))
    print()

    # 오늘 정보 추가
    today = date.today()
    iso_year, iso_week, iso_day = today.isocalendar()
    print(f"오늘: {today.isoformat()} ({WEEKDAY_KR[today.weekday()]}) W{iso_week:02d}")
    print(f"오늘 영업일 여부: {'예' if is_business_day(today) else '아니오'}")


if __name__ == "__main__":
    main()
