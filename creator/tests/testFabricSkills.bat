@echo off
REM Wrapper to run testskills-for-fabric.ps1 from the command line
powershell -ExecutionPolicy Bypass -File "%~dp0testskills-for-fabric.ps1" %*
