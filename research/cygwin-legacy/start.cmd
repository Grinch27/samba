@echo off
rem Open questions: Cygwin UID/SID mapping and NTFS ACL on target Windows.
rem Ambiguity: local Windows account names may differ from Cygwin names.
rem Follow-up: real Windows authentication and session identity tests.
rem Optimization: retain only required launch and account arguments.
rem Risk: private database contains password-equivalent hashes; never share it.
rem Verification: same smb.conf, absolute Cygwin root, fail on missing directories.
setlocal DisableDelayedExpansion
pushd "%~dp0" || exit /b 1
set "ROOT=%~dp0"
if not "%ROOT:~1,1%"==":" (
  echo Local drive path required. 1>&2
  popd
  exit /b 1
)
set "ROOT=%ROOT:\=/%"
set "SAMBA_PORTABLE_ROOT=/cygdrive/%ROOT:~0,1%%ROOT:~2,-1%"
set "PATH=%~dp0bin;%SystemRoot%\System32;%SystemRoot%"
if not exist "%~dp0smb.conf" goto missing
if not exist "%~dp0private\NUL" goto missing
for %%D in (state cache lock run rpc) do if not exist "%~dp0%%D\NUL" (
  mkdir "%~dp0%%D" || goto failed
)
if not exist "%~dp0bin\smbd.exe" goto missing
if not exist "%~dp0bin\testparm.exe" goto missing
if not exist "%~dp0private\passdb.tdb" goto missing
"%~dp0bin\testparm.exe" -s "%SAMBA_PORTABLE_ROOT%/smb.conf" >nul
if errorlevel 1 goto failed
"%~dp0bin\testparm.exe" -s --parameter-name="private dir" "%SAMBA_PORTABLE_ROOT%/smb.conf" | "%SystemRoot%\System32\findstr.exe" /I /L /X /C:"%SAMBA_PORTABLE_ROOT%/private" >nul
if errorlevel 1 (
  echo Set private dir and all other runtime directories to the actual package path in smb.conf. 1>&2
  goto failed
)
echo Running in foreground. Use Ctrl+C in this console to stop.
"%~dp0bin\smbd.exe" --foreground --no-process-group --debug-stdout --configfile="%SAMBA_PORTABLE_ROOT%/smb.conf"
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%

:missing
echo Missing program, smb.conf or manually ACL-protected private directory/database. 1>&2
:failed
popd
exit /b 1
