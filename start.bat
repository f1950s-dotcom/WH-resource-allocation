@echo off
chcp 65001 > nul
cd /d %~dp0

echo ============================================
echo  最新コードを取得しています (git pull)...
echo ============================================
git pull origin claude/busy-cori-b3y1om
echo.

echo バックエンドの依存関係を確認中...
cd /d %~dp0backend
python -m pip install -q -r requirements.txt
cd /d %~dp0

echo バックエンド起動中...
start "Backend" cmd /k "cd /d %~dp0backend && python -m uvicorn main:app --host 0.0.0.0 --port 8000"

timeout /t 2 /nobreak > nul

echo フロントエンドの依存関係を確認中...
cd /d %~dp0frontend
call npm install --silent
cd /d %~dp0

echo フロントエンド起動中...
start "Frontend" cmd /k "cd /d %~dp0frontend && npm run dev -- --host"

echo.
echo ============================================
echo  起動完了！
echo  バックエンド  : http://localhost:8000
echo  フロントエンド: http://localhost:5173
echo ============================================
echo ウィンドウを閉じると停止します。
