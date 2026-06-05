#!/bin/bash
FIFO=/tmp/claude_auth_input
rm -f $FIFO /tmp/claude_auth_output.txt /tmp/claude_code.txt
mkfifo $FIFO

TERM=xterm claude auth login < $FIFO > /tmp/claude_auth_output.txt 2>&1 &
PID=$!
exec 3>$FIFO

for i in $(seq 1 30); do
    sleep 1
    if grep -q 'claude.com' /tmp/claude_auth_output.txt 2>/dev/null; then
        grep -o 'https://[^ ]*' /tmp/claude_auth_output.txt | head -1
        echo "===URL_READY==="
        break
    fi
done

for i in $(seq 1 300); do
    sleep 1
    if [ -f /tmp/claude_code.txt ]; then
        CODE=$(cat /tmp/claude_code.txt)
        echo "$CODE" >&3
        sleep 1
        echo "===CODE_SENT==="
        break
    fi
done

exec 3>&-
wait $PID
echo "===AUTH_DONE==="
cat /tmp/claude_auth_output.txt
