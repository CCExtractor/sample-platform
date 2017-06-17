:: batch file for variables

:: This script contains the variables which we don't want to post on GitHub
:: Copy/rename this to variables, and fill this in.

@echo off
:: File that contains the URL to report to
set reportURLFile="/path/to/token/file"
:: Directory that contains the sources of the version to test
set srcDir="/path/to/ccextractor/repository"
:: Directory to copy the files to
set dstDir="/new/path/to/ccextractor/repository"
:: Directory where the test suite is located
set suiteSrcDir="/path/to/test/suite"
:: Directory where the test suite is located
set suiteDstDir="/path/to/test/suite"
:: Shell script to launch the test suite
set tester="./ccextractortester"
:: Location of the samples
set sampleFolder="/path/to/test/files"
:: Location of the result files
set resultFolder="/path/to/result/files"
:: Testfile location
set testFile="/path/to/testfile.xml"
:: The folder that will be used to store the results in
set reportFolder="/path/to/folder/"
:: The folder that will be used to temporarily store the result files in
set tempFolder="/path/to/temp/folder/"
