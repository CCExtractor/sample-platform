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
call :postStatus "preparation" "Loaded variables and creating log file"

for /F %%R in ('curl http://metadata/computeMetadata/v1/instance/attributes/reportURL -H "Metadata-Flavor: Google"') do SET reportURL=%%R
SET userAgent="CCX/CI_BOT"
SET logFile="%reportFolder%/log.html"

echo Checking for CCExtractor build artifact
call :postStatus "building" "Checking if CCExtractor build artifact is present"
if EXIST "%dstDir%\ccextractorwinfull.exe" (
    echo Run tests
    call :postStatus "testing" "Running tests"
    call :executeCommand cd %suiteDstDir%
    call :executeCommand "%tester%" --entries "%testFile%" --executable "%dstDir%\ccextractorwinfull.exe" --tempfolder "%tempFolder%" --timeout 3000 --reportfolder "%reportFolder%" --resultfolder "%resultFolder%" --samplefolder "%sampleFolder%" --method Server --url "%reportURL%"
    call :postStatus "completed" "Ran all tests"
    echo Done running tests

    timeout 5
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
EXIT /B 0

rem Exit script and post abort status
:haltAndCatchFire
echo "Halt and catch fire (reason: %~1)"
call :postStatus "canceled" "%~1"
timeout 5
echo Post log
curl -s -A "%userAgent%" --form "type=logupload" --form "file=@%logFile%" -w "\n" "%reportURL%"
rem Shut down, but only in 10 seconds, to give the time to finish the post status
timeout 10
shutdown -s -t 0
EXIT 0
