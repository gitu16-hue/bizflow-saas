@echo off
cd /d C:\ai_whatsapp_agent
call venv\Scripts\activate

echo Starting BizFlow Server...
start cmd /k uvicorn whatsapp_app:app --host 127.0.0.1 --port 8001 --reload

timeout /t 5

echo Starting Cloudflare Tunnel...
start cmd /k cloudflared tunnel run bizflow

echo ===============================
echo 🚀 BizFlow Platform Started
echo ===============================
pause
