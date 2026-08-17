@echo off
title ResearchGuard AI - Website
cd /d "%~dp0"
echo ============================================
echo  ResearchGuard AI - starting web server...
echo  The browser will open at http://127.0.0.1:5000
echo  (First start may take a minute - the AI model loads once.)
echo ============================================
start "" http://127.0.0.1:5000
python app.py
pause