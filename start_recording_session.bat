@echo off
chcp 65001 > nul
title TRIBAL ISLAND BOT - PASSIVE INPUT LOGGER
cls
echo ======================================================================
echo           TRIBAL ISLAND BOT - PASSIVE INPUT LOGGER (P2)
echo         Phương án 3: Ghi nhận phím thụ động kết hợp cùng OBS
echo ======================================================================
echo.
echo  [!] HƯỚNG DẪN 3 BƯỚC:
echo      1. Bật OBS / Trình quay màn hình BlueStacks (1920x1080).
echo      2. Logger này đang chạy ngầm để ghi nhận phím (KHÔNG làm lag game).
echo      3. Sau khi chơi xong, nhấn [Ctrl + C] tại cửa sổ này để lưu log.
echo.
echo ======================================================================
echo.
python core\demonstration\passive_input_logger.py
pause

