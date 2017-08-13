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
if "%reportURLFile%"=="" (
    rem No report URL file defined
    shutdown -s -t 0
    exit
)
if "%srcDir%"=="" (
    rem No source dir defined
    shutdown -s -t 0
    exit
)

SET /P reportURL=<%reportURLFile%
SET userAgent="CCX/CI_BOT"
SET logFile="%reportFolder%/log.html"

echo Copy files over to local disk
call :postStatus "preparation" "Copy testsuite to local folder"
rem robocopy returns a non-zero exit code even on success (https://ss64.com/nt/robocopy-exit.html), so we cannot use executeCommand
call robocopy %suiteSrcDir% %suiteDstDir% /e >> "%logFile%"

call :postStatus "preparation" "Copy code to local folder"
call robocopy %srcDir% %dstDir% /e >> "%logFile%"
call :executeCommand cd %dstDir%

echo Compile CCX using cmake
call :postStatus "building" "Compiling CCExtractor using cmake"
rem making a build folder
mkdir build
cd build
rem Compiling using cmake from src source to build repo
cmake ../src
rem Building CCExtractor
cmake --build . --config Debug --target ccextractor
if EXIST Debug\ccextractor.exe (
	call :postStatus "building" "Successful build using cmake"
)
else (
	call :postStatus "building" "Failed to build using cmake"
)
cd ..
rmdir /Q/S build

echo Compile CCX
call :postStatus "building" "Compiling CCExtractor"
rem Go to Windows build folder
call :executeCommand cd windows
rem Build CCExtractor using the sln script
call :executeCommand "C:\Program Files (x86)\MSBuild\14.0\Bin\MSBuild" ccextractor.sln
rem check whether installation successful
if EXIST Debug\ccextractorwin.exe (
    cd Debug
    rem Run testsuite
    echo Run tests
    call :postStatus "testing" "Running tests"
    call :executeCommand cd %suiteDstDir%
    call :executeCommand "%tester%" --entries "%testFile%" --executable "%dstDir%\windows\Debug\ccextractorwin.exe" --tempfolder "%tempFolder%" --timeout 3000 --reportfolder "%reportFolder%" --resultfolder "%resultFolder%" --samplefolder "%sampleFolder%" --method Server --url "%reportURL%"
    call :postStatus "completed" "Ran all tests"
    echo Done running tests
    rem Shut down
    timeout 5
    shutdown -s -t 0
    exit
)
else
(
    call :haltAndCatchFire "build"
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
