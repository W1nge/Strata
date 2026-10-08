@echo off
setlocal
call "C:\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
cl /nologo /std:c++20 /O2 /EHsc /I "E:\strata-setup\part2-prefix-20261008\upstream-pr\include" "E:\strata-setup\part2-prefix-20261008\upstream-pr\src\core\conversation_cache_test.cpp" /Fo"E:\strata-setup\part2-prefix-20261008\upstream-cache-test.obj" /Fe"E:\strata-setup\part2-prefix-20261008\upstream-cache-test.exe"
if errorlevel 1 exit /b 1
"E:\strata-setup\part2-prefix-20261008\upstream-cache-test.exe"
if errorlevel 1 exit /b 1
cl /nologo /std:c++20 /O2 /EHsc /I "E:\strata-setup\part2-prefix-20261008\upstream-pr\include" "E:\strata-setup\part2-prefix-20261008\upstream-pr\src\program\conv_cache_test.cpp" /Fo"E:\strata-setup\part2-prefix-20261008\upstream-retention-test.obj" /Fe"E:\strata-setup\part2-prefix-20261008\upstream-retention-test.exe"
if errorlevel 1 exit /b 1
"E:\strata-setup\part2-prefix-20261008\upstream-retention-test.exe"
exit /b %errorlevel%
