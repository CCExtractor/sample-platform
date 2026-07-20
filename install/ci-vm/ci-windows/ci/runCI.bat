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

rem NB: no outer ">> %logFile%" here. postStatus already appends to %logFile%
rem internally; an outer redirect to the same file self-locks on Windows
rem (the inner append cannot open a file the outer redirect holds open).
call :postStatus "preparation" "Loaded variables, created log file and checking for CCExtractor build artifact"

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

    rem Capture the test run's combined stdout/stderr for upload as an artifact.
    rem NB: "||" instead of "if errorlevel 1" - it fires at runtime on ANY
    rem nonzero exit code, including the negative NTSTATUS codes a crash
    rem returns, e.g. 0xC0000005, and works inside this parenthesized block
    rem where %ERRORLEVEL% would expand too early.
    set "testerFailed="
    "%tester%" --debug True --entries "%testFile%" --executable "ccextractorwinfull.exe" --tempfolder "%tempFolder%" --timeout 600 --reportfolder "%reportFolder%" --resultfolder "%resultFolder%" --samplefolder "%sampleFolder%" --method Server --url "%reportURL%" > "%reportFolder%/combined_stdout.log" 2>&1 || set "testerFailed=1"
    type "%reportFolder%/combined_stdout.log" >> "%logFile%"

    rem Upload artifacts (best-effort; never aborts the run). Windows skips coredump for v1.
    call :sendArtifact "binary" "%dstDir%\ccextractorwinfull.exe"
    call :sendArtifact "combined_stdout" "%reportFolder%/combined_stdout.log"

    if defined testerFailed call :haltAndCatchFire ""

    call :sendLogFile

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

rem Post status to the server with retry logic
:postStatus
setlocal EnableDelayedExpansion
set "ps_status=%~1"
set "ps_message=%~2"
set ps_attempt=1
set ps_max_retries=3
set ps_retry_delay=5

:postStatusRetry
echo "Posting status %ps_status% (message: %ps_message%) to the server (attempt !ps_attempt!/%ps_max_retries%)"
echo Posting status %ps_status% - %ps_message% (attempt !ps_attempt!/%ps_max_retries%) >> "%logFile%"

curl -s -A "%userAgent%" --data "type=progress&status=%ps_status%&message=%ps_message%" -w "%%{http_code}" -o "%TEMP%\curl_response.txt" "%reportURL%" > "%TEMP%\http_code.txt" 2>&1
set ps_curl_exit=%ERRORLEVEL%

set /p ps_http_code=<"%TEMP%\http_code.txt"

if %ps_curl_exit% EQU 0 (
    if !ps_http_code! GEQ 200 if !ps_http_code! LSS 300 (
        echo Status posted successfully (HTTP !ps_http_code!) >> "%logFile%"
        type "%TEMP%\curl_response.txt" >> "%logFile%" 2>nul
        echo. >> "%logFile%"
        timeout 5
        endlocal
        EXIT /B 0
    )
)

echo Attempt !ps_attempt!/%ps_max_retries% failed (curl exit: %ps_curl_exit%, HTTP: !ps_http_code!) >> "%logFile%"
set /A ps_attempt+=1

if !ps_attempt! LEQ %ps_max_retries% (
    echo Retrying in %ps_retry_delay% seconds... >> "%logFile%"
    timeout %ps_retry_delay%
    set /A ps_retry_delay*=2
    goto postStatusRetry
)

echo ERROR: Failed to post status after %ps_max_retries% attempts >> "%logFile%"
endlocal
EXIT /B 1

rem Exit script and post abort status
:haltAndCatchFire
echo "Halt and catch fire (reason: %~1)"
echo Post log
call :sendLogFile
call :postStatus "canceled" "%~1"
shutdown -s -t 0
EXIT 0

rem Send log file to server with retry logic
:sendLogFile
setlocal EnableDelayedExpansion
set sl_attempt=1
set sl_max_retries=3
set sl_retry_delay=5

:sendLogFileRetry
echo Sending log to server (attempt !sl_attempt!/%sl_max_retries%) >> "%logFile%"

curl -s -A "%userAgent%" --form "type=logupload" --form "file=@%logFile%" -w "%%{http_code}" -o "%TEMP%\curl_log_response.txt" "%reportURL%" > "%TEMP%\log_http_code.txt" 2>&1
set sl_curl_exit=%ERRORLEVEL%

set /p sl_http_code=<"%TEMP%\log_http_code.txt"

if %sl_curl_exit% EQU 0 (
    if !sl_http_code! GEQ 200 if !sl_http_code! LSS 300 (
        echo Log uploaded successfully (HTTP !sl_http_code!) >> "%logFile%"
        timeout 5
        endlocal
        EXIT /B 0
    )
)

echo Log upload attempt !sl_attempt!/%sl_max_retries% failed (curl exit: %sl_curl_exit%, HTTP: !sl_http_code!) >> "%logFile%"
set /A sl_attempt+=1

if !sl_attempt! LEQ %sl_max_retries% (
    echo Retrying log upload in %sl_retry_delay% seconds... >> "%logFile%"
    timeout %sl_retry_delay%
    set /A sl_retry_delay*=2
    goto sendLogFileRetry
)

echo ERROR: Failed to upload log after %sl_max_retries% attempts >> "%logFile%"
endlocal
EXIT /B 1

rem Send a build artifact to the server (best-effort; never aborts the run)
:sendArtifact
setlocal
set "sa_type=%~1"
set "sa_file=%~2"
if NOT EXIST "%sa_file%" (
    echo Artifact %sa_type%: no file at "%sa_file%", skipping >> "%logFile%"
    endlocal
    EXIT /B 0
)
echo Uploading %sa_type% artifact (%sa_file%) >> "%logFile%"
rem --fail makes HTTP >= 400 (e.g. 413 on an oversized file) a curl error so
rem the failure is at least visible in the log; the upload stays best-effort.
curl -s --fail -A "%userAgent%" --form "type=artifactupload" --form "artifact_type=%sa_type%" --form "file=@%sa_file%" "%reportURL%" >> "%logFile%" 2>&1
if errorlevel 1 echo Artifact %sa_type%: upload failed with curl exit code %ERRORLEVEL% >> "%logFile%"
endlocal
EXIT /B 0
