:: batch file for variables

:: This script contains the variables which are used during CI on VM instances.
:: Copy/rename this file in case you want to change the default variables.

@echo off
:: Directory where ccextractor executable is located
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
