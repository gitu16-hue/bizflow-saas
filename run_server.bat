@echo off
cd /d C:\ai_whatsapp_agent
call venv\Scripts\activate

uvicorn whatsapp_app:app --host 127.0.0.1 --port 8001 --reload

pause
