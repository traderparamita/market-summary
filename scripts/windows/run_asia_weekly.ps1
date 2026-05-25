$ROOT   = "c:\Users\user\Desktop\kosmos\market-summary"
$LOG    = "$ROOT\logs\asia_weekly.log"
$PYTHON = "$ROOT\.venv\Scripts\python.exe"
$SCRIPT = "$ROOT\scripts\generate_asia_weekly.py"

$env:PYTHONUTF8       = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
# claude CLI 경로를 PATH에 추가 (Task Scheduler는 사용자 PATH를 상속하지 않을 수 있음)
$env:PATH = "C:\Users\user\.local\bin;$env:PATH"

"" | Out-File -Append -Encoding utf8 $LOG
"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss KST') ===" | Out-File -Append -Encoding utf8 $LOG
& $PYTHON $SCRIPT 2>&1 | Out-File -Append -Encoding utf8 $LOG
