rem chrome.exe --remote-debugging-port=9222 --user-data-dir=C:\temp
set filepath1="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
set filepath2="C:\Program Files\Google\Chrome\Application\chrome.exe"
if exist %filepath1% (
    start "chrome" %filepath1% --remote-debugging-port=9223
) else (
    start "chrome" %filepath2% --remote-debugging-port=9223
)
