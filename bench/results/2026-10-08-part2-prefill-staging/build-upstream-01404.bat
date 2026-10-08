@echo off
setlocal
call "C:\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
"C:\Users\Winge\AppData\Roaming\Python\Python313\site-packages\cmake\data\bin\cmake.exe" --build "E:\strata-setup\part2-dual\build" --target strata file_expert_source_test mmvq_multi_parity pdl_parity native_expert_parity --parallel 4
exit /b %errorlevel%
