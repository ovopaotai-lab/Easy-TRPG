@echo off
chcp 65001 >nul
title AI 跑团 (alpha 1.4)
cd /d "%~dp0"
call "%~dp0run.bat" %*
