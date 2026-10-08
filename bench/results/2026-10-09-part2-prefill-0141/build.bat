@echo off
setlocal
call "C:\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
set "PATH=E:\strata-setup\cuda-portable\bin;%PATH%"
cl /nologo /std:c++20 /O2 /EHsc /I "C:\Users\Winge\Documents\Playground\Strata-optimization-pr\include" "C:\Users\Winge\Documents\Playground\Strata-optimization-pr\src\core\conversation_cache_test.cpp" /Fo"E:\strata-setup\part2-prefill-0141-20261009\conversation-cache.obj" /Fe"E:\strata-setup\part2-prefill-0141-20261009\conversation-cache.exe"
if errorlevel 1 exit /b 1
"E:\strata-setup\part2-prefill-0141-20261009\conversation-cache.exe"
if errorlevel 1 exit /b 1
cl /nologo /std:c++20 /O2 /EHsc /I "C:\Users\Winge\Documents\Playground\Strata-optimization-pr\include" "C:\Users\Winge\Documents\Playground\Strata-optimization-pr\src\program\conv_cache_test.cpp" /Fo"E:\strata-setup\part2-prefill-0141-20261009\retention.obj" /Fe"E:\strata-setup\part2-prefill-0141-20261009\retention.exe"
if errorlevel 1 exit /b 1
"E:\strata-setup\part2-prefill-0141-20261009\retention.exe"
if errorlevel 1 exit /b 1
"C:\Users\Winge\AppData\Roaming\Python\Python313\site-packages\cmake\data\bin\cmake.exe" --build "E:\strata-setup\part2-dual\build" --target strata file_expert_source_test gr_parity --parallel 4
exit /b %errorlevel%
