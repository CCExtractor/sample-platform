: batch file for variables

:: This script contains the variables which we don't want to post on GitHub
:: Copy/rename this to variables, and fill this in.

@echo off
:: Directory to copy the files to
set dstDir=.\vm_data\unsafe-ccextractor
:: Directory where the test suite is located
set suiteDstDir=.
:: Shell script to launch the test suite
set tester=.\ccextractortester
:: Location of the samples
set sampleFolder=.\TestFiles
:: Location of the result files
set resultFolder=.\TestResults
:: Testfile location
set testFile=.\vm_data\ci-tests\TestAll.xml
:: The folder that will be used to store the results in
set reportFolder=.\reports