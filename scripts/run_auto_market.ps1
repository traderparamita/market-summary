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
