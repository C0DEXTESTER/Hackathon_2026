@echo off
REM ============================================================
REM  Double-click this file to run the AI Research Paper
REM  Similarity Prototype without opening a terminal manually.
REM ============================================================

REM Move into the folder where this .bat file lives
cd /d "%~dp0"

echo ===========================================
echo  AI RESEARCH PAPER SIMILARITY PROTOTYPE
echo ===========================================
echo.

REM Run the main program
python main.py

echo.
echo Full results were saved to: results\analysis.json
echo.
pause