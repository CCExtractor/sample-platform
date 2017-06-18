:: batch file
@echo off

if NOT EXIST "variables.bat" (
    :: No variable file defined
    shutdown -s -t 0
)
:: Source variables
call variables.bat
if NOT EXIST %reportURLFile% (
    :: No report URL file defined
    shutdown -s -t 0
)
if NOT EXIST %srcDir% (
    :: No source dir defined
    shutdown -s -t 0
)

SET /P reportURL=<%reportURLFile%
SET userAgent="CCX/CI_BOT"
SET logFile="%reportFolder%/log.html"

call :postStatus "preparation" "Copy testsuite to local folder"
call :executeCommand robocopy %srcDir% %dstDir% /e
call :executeCommand cd %dstDir%

call :postStatus "building" "Compiling CCExtractor"
:: Go to Windows build folder
call :executeCommand cd windows
:: Build CCExtractor using the sln script
call :executeCommand "C:\Program Files (x86)\MSBuild\14.0\Bin\MSBuild" ccextractor.sln
:: check whether installation successful
if EXIST Debug\ccextractorwin.exe (
    cd Debug
    :: Run testsuite
    call :postStatus "testing" "Running tests"
    call :executeCommand cd %suiteDstDir%
    call :executeCommand "%tester%" --entries "%testFile%" --executable "%dstDir%/windows/Debug/ccextractor" --tempfolder "%tempFolder%" --timeout 3000 --reportfolder "%reportFolder%" --resultfolder "%resultFolder%" --samplefolder "%sampleFolder%" --method Server --url "%reportURL%"
    call :postStatus "completed" "Ran all tests"
    :: Shut down
    shutdown -s -t 0
)
else
(
    call :haltAndCatchFire "build"
)
EXIT /B %ERRORLEVEL%
:: Functions to shorten the script

:: Fail when the exit status is not equal to 0
:executeCommand
%* > "%logFile%"
SET /A status=%ERRORLEVEL%
IF %status% NEQ 0 (
    :: No message needed as we post before anyway
    call :haltAndCatchFire ""
)
EXIT /B 0

:: Post status to the server
:postStatus
curl -s -A "%userAgent%" --data "type=progress&status=%~1&message=%~2" -w "\n" "%reportURL%" >> "%logFile%"
EXIT /B 0

:: Exit script and post abort status
:haltAndCatchFire
call :postStatus "canceled" %~1 >> "%logFile%"
shutdown -s -t 0
EXIT /B 0

