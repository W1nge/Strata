@echo off
setlocal
call "C:\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
cl /nologo /std:c++20 /O2 /EHsc /I "C:\Users\Winge\Documents\Playground\Strata-optimization-pr\include" "C:\Users\Winge\Documents\Playground\Strata-optimization-pr\src\core\conversation_cache_test.cpp" /Fo"E:\strata-setup\part2-prefix-20261008\conversation_cache_test.obj" /Fe"E:\strata-setup\part2-prefix-20261008\conversation_cache_test.exe"
if errorlevel 1 exit /b 1
"E:\strata-setup\part2-prefix-20261008\conversation_cache_test.exe"
if errorlevel 1 exit /b 1
"C:\Users\Winge\AppData\Roaming\Python\Python313\site-packages\cmake\data\bin\cmake.exe" --build "E:\strata-setup\part2-dual\build" --target strata --parallel 4
exit /b %errorlevel%
