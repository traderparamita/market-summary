# setup_windows_tasks.ps1
# Windows 작업 스케줄러에 Market Summary 자동화 4개 태스크를 등록한다.
# 관리자 권한 없이 현재 사용자 세션에서 실행 가능 (LogonType: InteractiveToken).
#
# 사용법:
#   powershell -ExecutionPolicy Bypass -File scripts\windows\setup_windows_tasks.ps1
#
# 재실행 시 기존 태스크를 -Force 로 덮어쓴다.

$ROOT = "c:\Users\user\Desktop\kosmos\market-summary"

$TASKS = @(
    @{ Name = "MarketSummary-Daily";          XML = "$ROOT\scripts\windows\market_summary_task.xml" },
    @{ Name = "MarketSummary-OCR";            XML = "$ROOT\scripts\windows\market_ocr_task.xml" },
    @{ Name = "MarketSummary-WeeklyCollect";  XML = "$ROOT\scripts\windows\securities_reports_task.xml" },
    @{ Name = "MarketSummary-AsiaWeekly";     XML = "$ROOT\scripts\windows\asia_weekly_task.xml" },
    @{ Name = "MarketSummary-DailyResearch";  XML = "$ROOT\scripts\windows\daily_research_task.xml" }
)

Write-Host ""
Write-Host "=== Market Summary Windows Task 등록 ===" -ForegroundColor Cyan
Write-Host ""

$allOk = $true

foreach ($t in $TASKS) {
    Write-Host "[$($t.Name)]" -ForegroundColor Yellow

    if (-not (Test-Path $t.XML)) {
        Write-Host "  [ERROR] XML 없음: $($t.XML)" -ForegroundColor Red
        $allOk = $false
        continue
    }

    try {
        $xmlContent = Get-Content -Path $t.XML -Raw -Encoding UTF8
        # Register-ScheduledTask 는 PowerShell 내부 UTF-16 문자열을 받으므로
        # <?xml ... encoding="UTF-8"?> 선언이 있으면 인코딩 충돌 오류 발생.
        # 선언 줄을 제거하고 전달한다.
        $xmlContent = $xmlContent -replace '^\s*<\?xml[^?]*\?>\s*', ''
        Register-ScheduledTask -TaskName $t.Name -Xml $xmlContent -Force -ErrorAction Stop | Out-Null
        Write-Host "  OK - 등록 완료" -ForegroundColor Green
    } catch {
        Write-Host "  [ERROR] $_" -ForegroundColor Red
        $allOk = $false
    }
    Write-Host ""
}

Write-Host "=== 등록된 MarketSummary 태스크 ===" -ForegroundColor Cyan
Get-ScheduledTask | Where-Object { $_.TaskName -like "MarketSummary-*" } | ForEach-Object {
    $info = Get-ScheduledTaskInfo -TaskName $_.TaskName -ErrorAction SilentlyContinue
    $next = if ($info -and $info.NextRunTime) { $info.NextRunTime.ToString("yyyy-MM-dd HH:mm") } else { "-" }
    Write-Host ("  {0,-35} 다음실행: {1}" -f $_.TaskName, $next)
}

Write-Host ""
if ($allOk) {
    Write-Host "완료: 5개 태스크 모두 등록됨." -ForegroundColor Green
} else {
    Write-Host "일부 태스크 등록 실패. 위 오류를 확인하세요." -ForegroundColor Red
}
Write-Host ""
Write-Host "수동 실행 테스트:"
Write-Host "  schtasks /Run /TN MarketSummary-Daily"
Write-Host "  schtasks /Run /TN MarketSummary-OCR"
Write-Host "  schtasks /Run /TN MarketSummary-WeeklyCollect"
Write-Host "  schtasks /Run /TN MarketSummary-AsiaWeekly"
Write-Host "  schtasks /Run /TN MarketSummary-DailyResearch"
