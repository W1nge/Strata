@echo off
setlocal
call "C:\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
"C:\Users\Winge\AppData\Roaming\Python\Python313\site-packages\cmake\data\bin\cmake.exe" --build "E:\strata-setup\part2-dual\build" --target strata --parallel 4
exit /b %errorlevel%
