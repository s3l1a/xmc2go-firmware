@echo off
setlocal enabledelayedexpansion
rem Build and run the C known-answer vectors with MSVC cl.exe or gcc.
rem Usage: run_c_vectors.bat          (from anywhere)
rem        run_c_vectors.bat --build   (build only)

set HERE=%~dp0
set ROOT=%HERE%..\..
pushd "%HERE%"

where cl >nul 2>&1
if not errorlevel 1 goto :msvc

rem try vswhere to locate MSVC
set VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe
if exist "%VSWHERE%" (
  for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do (
    call "%%i\VC\Auxiliary\Build\vcvars32.bat" >nul 2>&1
  )
)
where cl >nul 2>&1
if not errorlevel 1 goto :msvc

where gcc >nul 2>&1
if not errorlevel 1 goto :gcc

echo FAIL: neither MSVC cl.exe nor gcc found on this machine
popd
exit /b 2

:msvc
if not defined VCINSTALLDIR (
  call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars32.bat" >nul 2>&1
)
cl /nologo /std:c11 /W3 /I"%ROOT%\common" /I"%ROOT%\board" c_vectors.c "%ROOT%\common\crc16.c" "%ROOT%\common\crc32.c" "%ROOT%\board\flash.c" /Fe:c_vectors.exe
if errorlevel 1 (
  echo FAIL: compilation failed
  popd
  exit /b 1
)
if "%1"=="--build" (popd & exit /b 0)
c_vectors.exe
set RC=!ERRORLEVEL!
popd
exit /b %RC%

:gcc
gcc -std=c11 -Wall -Wextra -I"%ROOT%\common" -I"%ROOT%\board" c_vectors.c "%ROOT%\common\crc16.c" "%ROOT%\common\crc32.c" "%ROOT%\board\flash.c" -o c_vectors.exe
if errorlevel 1 (
  echo FAIL: compilation failed
  popd
  exit /b 1
)
if "%1"=="--build" (popd & exit /b 0)
c_vectors.exe
set RC=!ERRORLEVEL!
popd
exit /b %RC%
