@echo off
rem Build io_scene_fbx_layers\lib\fbxl_ufbx_windows_x64.dll with MSVC (x64).
rem Run from a "x64 Native Tools Command Prompt", or this script finds vcvars64 through vswhere.
setlocal
cd /d "%~dp0"
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
where cl >nul 2>nul && goto build
for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSDIR=%%i"
call "%VSDIR%\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1

:build
if not exist build mkdir build
cl /nologo /O2 /LD /MT /Fobuild\ fbxl_ufbx.c ufbx\ufbx.c /Fe:..\io_scene_fbx_layers\lib\fbxl_ufbx_windows_x64.dll /link /NOIMPLIB /NOEXP || exit /b 1
