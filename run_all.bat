@echo off
chcp 936 >nul
title Extractor

:menu
cls
echo ========================================
echo     Invoice and Order Extractor
echo ========================================
echo.
echo   --- Invoice ---
echo   [1] Local (PyMuPDF text parsing)
echo   [2] Qwen Vision Model
echo   [3] DeepSeek-OCR + Regex
echo.
echo   --- Order Screenshot ---
echo   [4] Local (EasyOCR)
echo   [5] Qwen Vision Model
echo   [6] EasyOCR + Qwen Merge
echo.
echo   --- Merge ---
echo   [10] Invoice Cross-Vote Merge (3 engines)
echo.
echo   --- Batch ---
echo   [7] Run ALL
echo   [8] Run Invoice Only (all 3 methods)
echo   [9] Run Order Only (all 3 methods)
echo.
echo   [0] Exit
echo.
echo ========================================
echo.

set /p choice=  Select [0-9]:

if "%choice%"=="1" goto inv_local
if "%choice%"=="2" goto inv_qwen
if "%choice%"=="3" goto inv_deepseek
if "%choice%"=="4" goto order_local
if "%choice%"=="5" goto order_qwen
if "%choice%"=="6" goto order_merge
if "%choice%"=="7" goto all
if "%choice%"=="8" goto inv_all
if "%choice%"=="9" goto order_all
if "%choice%"=="10" goto invoice_merge
if "%choice%"=="0" goto end

echo Invalid choice, try again.
pause
goto menu

:inv_local
echo.
echo [Invoice - Local PyMuPDF]
python extract_invoices.py
echo.
pause
goto menu

:inv_qwen
echo.
echo [Invoice - Qwen Vision Model]
python ollama_invoice_ocr.py
echo.
pause
goto menu

:inv_deepseek
echo.
echo [Invoice - DeepSeek-OCR + Regex]
python deepseek_invoice_ocr.py
echo.
pause
goto menu

:order_local
echo.
echo [Order - EasyOCR]
python extract_orders.py
echo.
pause
goto menu

:order_qwen
echo.
echo [Order - Qwen Vision Model]
python ollama_order_ocr.py
echo.
pause
goto menu

:order_merge
echo.
echo [Order - EasyOCR + Qwen Merge]
python combined_order_ocr.py
echo.
pause
goto menu

:all
echo.
echo [1/6] Invoice - Local...
python extract_invoices.py
echo.
echo [2/6] Invoice - Qwen Vision...
python ollama_invoice_ocr.py
echo.
echo [3/6] Invoice - DeepSeek-OCR + Regex...
python deepseek_invoice_ocr.py
echo.
echo [4/6] Order - EasyOCR...
python extract_orders.py
echo.
echo [5/6] Order - Qwen Vision...
python ollama_order_ocr.py
echo.
echo [6/6] Order - EasyOCR + Qwen Merge...
python combined_order_ocr.py
echo.
echo ========================================
echo           ALL DONE!
echo ========================================
echo.
pause
goto menu

:inv_all
echo.
echo [1/3] Invoice - Local...
python extract_invoices.py
echo.
echo [2/3] Invoice - Qwen Vision...
python ollama_invoice_ocr.py
echo.
echo [3/3] Invoice - DeepSeek-OCR + Regex...
python deepseek_invoice_ocr.py
echo.
echo ========================================
echo       INVOICE ALL DONE!
echo ========================================
echo.
pause
goto menu

:order_all
echo.
echo [1/3] Order - EasyOCR...
python extract_orders.py
echo.
echo [2/3] Order - Qwen Vision...
python ollama_order_ocr.py
echo.
echo [3/3] Order - EasyOCR + Qwen Merge...
python combined_order_ocr.py
echo.
echo ========================================
echo        ORDER ALL DONE!
echo ========================================
echo.
pause
goto menu

:invoice_merge
echo.
echo [Invoice Cross-Vote Merge]
python merge_invoice_ocr.py
echo.
pause
goto menu

:end
