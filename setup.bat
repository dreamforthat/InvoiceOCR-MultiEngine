@echo off
chcp 936 >nul
title Environment Setup
echo ========================================
echo     Invoice OCR - Environment Setup
echo ========================================
echo.

echo [1/5] Checking Python...
python --version
if errorlevel 1 (
    echo ERROR: Python not found!
    pause
    exit /b 1
)
echo.

echo [2/5] Installing PyTorch CUDA 12.8...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
echo.

echo [3/5] Installing OCR libraries...
pip install easyocr
echo.

echo [4/5] Installing PDF and image libraries...
pip install PyMuPDF Pillow requests
echo.

echo [5/5] Checking Ollama...
curl -s http://localhost:11434/api/tags >/dev/null 2>&1
if errorlevel 1 (
    echo WARNING: Ollama not running!
    echo Install: https://ollama.com/download
    echo Then run: ollama pull minicpm-v:8b
) else (
    echo Ollama is running
)
echo.

echo ========================================
echo           Setup Complete!
echo ========================================
echo.

echo Installed:
echo   PyTorch 2.11 + CUDA 12.8 (GPU)
echo   EasyOCR (Chinese + English)
echo   PyMuPDF (PDF processing)
echo   Pillow (Image processing)
echo.
echo Next: double-click run_all.bat
echo.
pause
