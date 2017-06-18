rem Place this script in the startup folder (e.g. C:\Users\[Username]\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup)
rem Depending on the setup, it will need to be modified.
rem E.g In the case of the live server, we use a network mount, so we need to add a "net use ..." command.

timeout 5
net use Z: \\path\to\network\mount
timeout 5

rem Modify this path to the path of your runCI.bat file
cd C:\Users\ci\Documents\ci
call runCI.bat