$ROOT   = "c:\Users\user\Desktop\kosmos\market-summary"
$LOG    = "$ROOT\logs\auto_market.log"
$PYTHON = "$ROOT\.venv\Scripts\python.exe"
$SCRIPT = "$ROOT\scripts\auto_market.py"

$env:PYTHONUTF8       = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"

"" | Out-File -Append -Encoding utf8 $LOG
"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss KST') ===" | Out-File -Append -Encoding utf8 $LOG
& $PYTHON $SCRIPT 2>&1 | Out-File -Append -Encoding utf8 $LOG
$MSExit = $LASTEXITCODE

# === Chain: Avalon morning brief — market-summary 가 RDS+ledger 적재를 끝낸 직후 실행 ===
# Avalon 은 이 데이터(mkt100/mkt200 + catalysts/completed.jsonl)의 reader 이므로 고정 시각 대신
# 연쇄로 걸어 항상 fresh 데이터로 돌게 한다. Avalon 자체 preflight 가 freshness 2차 게이트이므로
# MS 가 실패/부분성공이어도 Avalon 이 stale 을 판단해 그래도 진행(웹 배너)한다 → 무조건 연쇄.
$AvalonWrapper = "c:\Users\user\Desktop\kosmos\avalon\scripts\run_morning_brief.ps1"
"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss KST') chain -> Avalon (market-summary exit=$MSExit) ===" | Out-File -Append -Encoding utf8 $LOG
if (Test-Path $AvalonWrapper) {
    & $AvalonWrapper
    "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss KST') Avalon chain done (exit=$LASTEXITCODE) ===" | Out-File -Append -Encoding utf8 $LOG
} else {
    "!!! Avalon wrapper not found: $AvalonWrapper -- chain skipped" | Out-File -Append -Encoding utf8 $LOG
}

# === Chain: soul-autobiography 다음 주 전망 — Avalon 브리프 직후 (토요일만) ===
# 전망은 '다음 주' 준비라 주 1회면 충분 → 이 체인이 도는 화~금·토 중 토요일 실행분만 게이트한다
# (평일엔 '다가오는 월요일'이 다음다음주를 가리켜 부적절). soul 의 run_outlook.bat 이 헤드리스 claude
# 로 /outlook 을 돌려 회고(market-summary)·전망(avalon)·독립분석+WebSearch 를 종합해 생성·커밋·푸시.
if ((Get-Date).DayOfWeek -eq 'Saturday') {
    $OutlookBat = "c:\Users\user\Desktop\kosmos\soul-autobiography\scripts\run_outlook.bat"
    "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss KST') chain -> soul outlook ===" | Out-File -Append -Encoding utf8 $LOG
    if (Test-Path $OutlookBat) {
        & cmd /c "`"$OutlookBat`""
        "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss KST') soul outlook chain done (exit=$LASTEXITCODE) ===" | Out-File -Append -Encoding utf8 $LOG
    } else {
        "!!! soul outlook bat not found: $OutlookBat -- chain skipped" | Out-File -Append -Encoding utf8 $LOG
    }
}
