@echo off
title Smart Bazaar Runner
echo ========================================================
echo               SMART BAZAAR LAUNCHER
echo ========================================================
echo 1. Run Flutter App in Chrome (Recommended - instant view)
echo 2. Run Flutter App on Windows Desktop
echo 3. Run Flutter App on Connected Android Device / Emulator
echo 4. Install Release APK to Connected Android Device
echo 5. Open Django Admin in Default Browser
echo ========================================================
set /p choice="Select an option (1-5): "

if "%choice%"=="1" (
    echo Launching Smart Bazaar on Chrome...
    cd mobile
    "E:\flutter\bin\flutter.bat" run -d chrome --web-port=3000
) else if "%choice%"=="2" (
    echo Launching Smart Bazaar on Windows...
    cd mobile
    "E:\flutter\bin\flutter.bat" run -d windows
) else if "%choice%"=="3" (
    echo Launching Smart Bazaar on Android...
    cd mobile
    "E:\flutter\bin\flutter.bat" run -d android
) else if "%choice%"=="4" (
    echo Installing release APK...
    adb install -r "mobile\build\app\outputs\flutter-apk\app-release.apk"
    echo Installation complete! Check your phone.
    pause
) else if "%choice%"=="5" (
    echo Opening Django Admin in browser...
    start http://127.0.0.1:8000/admin/
) else (
    echo Invalid choice.
)

