@echo off

echo Checking for the existence of variables.bat
if NOT EXIST "variables.bat" (
    rem No variable file defined
    shutdown -s -t 0
    exit
)

echo Loading variables.bat
rem Source variables
call %~dp0\variables.bat

for /F %%R in ('curl http://metadata/computeMetadata/v1/instance/attributes/reportURL -H "Metadata-Flavor: Google"') do SET reportURL=%%R
SET userAgent="CCX/CI_BOT"
SET logFile="%reportFolder%/log.html"

call :postStatus "preparation" "Loaded variables, created log file and checking for CCExtractor build artifact" >> "%logFile%"

echo Checking for CCExtractor build artifact
if EXIST "%dstDir%\ccextractorwinfull.exe" (
    echo Run tests
    copy "%dstDir%\*" .
    rem Log binary version for verification (commit SHA will be visible in output)
    echo === CCExtractor Binary Version === >> "%logFile%"
    ccextractorwinfull.exe --version >> "%logFile%" 2>&1
    echo === End Version Info === >> "%logFile%"
    call :postStatus "testing" "Running tests"
    call :executeCommand cd %suiteDstDir%
    call :executeCommand "%tester%" --debug True --entries "%testFile%" --executable "ccextractorwinfull.exe" --tempfolder "%tempFolder%" --timeout 600 --reportfolder "%reportFolder%" --resultfolder "%resultFolder%" --samplefolder "%sampleFolder%" --method Server --url "%reportURL%"

    curl -s -A "%userAgent%" --form "type=logupload" --form "file=@%logFile%" -w "\n" "%reportURL%" >> "%logFile%"
    timeout 10

    echo Done running tests
    call :postStatus "completed" "Ran all tests"

    shutdown -s -t 0
    exit
) else (
    call :haltAndCatchFire "artifact"
)
echo End
EXIT %ERRORLEVEL%
rem Functions to shorten the script

rem Fail when the exit status is not equal to 0
:executeCommand
echo %* >> "%logFile%"
%* >> "%logFile%"
SET /A status=%ERRORLEVEL%
IF %status% NEQ 0 (
    echo Command exited with %status% >> "%logFile%"
    rem No message needed as we post before anyway
    call :haltAndCatchFire ""
)
EXIT /B 0

rem Post status to the server
:postStatus
echo "Posting status %~1 (message: %~2) to the server"
curl -s -A "%userAgent%" --data "type=progress&status=%~1&message=%~2" -w "\n" "%reportURL%" >> "%logFile%"
timeout 10
EXIT /B 0

rem Exit script and post abort status
:haltAndCatchFire
echo "Halt and catch fire (reason: %~1)"
echo Post log
curl -s -A "%userAgent%" --form "type=logupload" --form "file=@%logFile%" -w "\n" "%reportURL%" >> "%logFile%"
rem Shut down, but only in 10 seconds, to give the time to finish the post status
timeout 10
call :postStatus "canceled" "%~1"
shutdown -s -t 0
EXIT 0
