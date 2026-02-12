@echo off

set DATE=%date:~-4%%date:~4,2%%date:~7,2%

copy C:\ai_whatsapp_agent\bizflow.db C:\ai_whatsapp_agent\backups\bizflow_%DATE%.db

echo Backup done: %DATE%
