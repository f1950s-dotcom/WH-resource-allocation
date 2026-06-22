@echo off
echo バックエンド起動中...
start "Backend" cmd /k "cd /d %~dp0backend && python -m uvicorn main:app --host 0.0.0.0 --port 8000"

timeout /t 2 /nobreak > nul

echo フロントエンド起動中...
start "Frontend" cmd /k "cd /d %~dp0frontend && npm run dev -- --host"

echo.
echo 起動完了！
echo バックエンド: http://localhost:8000
echo フロントエンド: http://localhost:5173
echo.
echo ウィンドウを閉じると停止します。
