@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo 고객코드를 입력하면 issued_licenses\고객코드.txt로 저장됩니다.
echo 고객코드는 영문 또는 숫자로 시작하고 영문, 숫자, 밑줄, 하이픈만 사용할 수 있습니다.
echo.

if exist "%~dp0..\FREE\.venv\Scripts\python.exe" (
  "%~dp0..\FREE\.venv\Scripts\python.exe" -c "import cryptography" >nul 2>&1
  if not errorlevel 1 (
    "%~dp0..\FREE\.venv\Scripts\python.exe" "%~dp0PRO_CODE_TOOL.py"
    if errorlevel 1 goto finish
    goto done
  )
)

if exist "%~dp0..\PRO\.venv\Scripts\python.exe" (
  "%~dp0..\PRO\.venv\Scripts\python.exe" -c "import cryptography" >nul 2>&1
  if not errorlevel 1 (
    "%~dp0..\PRO\.venv\Scripts\python.exe" "%~dp0PRO_CODE_TOOL.py"
    if errorlevel 1 goto finish
    goto done
  )
)

py -3 -c "import cryptography" >nul 2>&1
if not errorlevel 1 (
  py -3 "%~dp0PRO_CODE_TOOL.py"
  if errorlevel 1 goto finish
  goto done
)

python -c "import cryptography" >nul 2>&1
if not errorlevel 1 (
  python "%~dp0PRO_CODE_TOOL.py"
  if errorlevel 1 goto finish
  goto done
)
goto missing_python

:missing_python
echo 라이선스 발급에 필요한 Python 환경이 없습니다.
echo 먼저 FREE 또는 PRO 폴더의 ONE_CLICK_START.bat을 한 번 실행한 뒤 다시 시도하세요.
goto finish

:done
echo.
echo 표시된 PRO CODE 전체를 고객에게 보내세요.
echo 발급 파일은 issued_licenses 폴더에 입력한 고객코드.txt로 저장됩니다.

:finish
pause
