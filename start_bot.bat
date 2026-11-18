@echo off
chcp 65001 > nul
title TRIBAL ISLAND BOT - AUTONOMOUS HYBRID AGENT
cls
echo ======================================================================
echo       TRIBAL ISLAND BOT - AUTONOMOUS HYBRID AGENT (LEVEL 3)
echo ======================================================================
echo.
echo  [!] Lưu ý trước khi chạy:
echo      1. Mở BlueStacks 5 và vào game Tribal Island (ở Sảnh hoặc trong trận).
echo      2. Đảm bảo đã bật ADB trong:
echo         BlueStacks Settings ^> Cài đặt nâng cao ^> Android Debug Bridge (ADB).
echo      3. Bot điều khiển ngầm 100%% qua ADB - KHÔNG chiếm chuột/bàn phím!
echo.
echo ======================================================================
echo.
python run_hybrid.py
pause

