@echo off
setlocal
set "PATH=E:\strata-setup\cuda-portable\bin;%PATH%"
set "STRATA_CPU_PROFILE="
set "STRATA_DECODE_TIMING="
set "STRATA_TRACE="
set "STRATA_LOGPOS="
set "STRATA_STATE_HASH="
set "STRATA_SNAPSHOT_VERIFY="
cd /d "C:\Users\Winge\.zcode\workspace\default\Strata"
"C:\ProgramData\anaconda3\python.exe" -m serve.server --engine strata --config "%~dp0strata-dual-p100-coding.json" --host 127.0.0.1 --port 8080 --open
if errorlevel 1 pause
endlocal
