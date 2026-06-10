@echo off
REM ============================================================
REM   Gridalytics — Weekly Training Pipeline (one-click)
REM   Run every Friday 23:00 IST
REM   Double-click this file. Wait ~15-20 min. Verify "PIPELINE COMPLETE".
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ============================================================
echo   GRIDALYTICS WEEKLY TRAINING — %DATE% %TIME%
echo ============================================================
echo.

REM --- 1. Sync latest code from main -------------------------
echo [1/6] Pulling latest code from main...
git fetch origin
git pull --ff-only
if errorlevel 1 (
    echo.
    echo ERROR: git pull failed. Resolve conflicts manually, then re-run.
    pause
    exit /b 1
)

REM --- 2. Ensure deps are installed ---------------------------
echo.
echo [2/6] Checking Python deps...
python -c "import lightgbm, xgboost, sqlalchemy, fastapi" 2>nul
if errorlevel 1 (
    echo Installing requirements...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: pip install failed.
        pause
        exit /b 1
    )
)

REM --- 3. Run the pipeline ------------------------------------
echo.
echo [3/6] Running full pipeline (scrape + train + predict)...
echo This will take 15-20 minutes. Do not close this window.
echo.
python scripts\run_full_pipeline.py
if errorlevel 1 (
    echo.
    echo ============================================================
    echo   PIPELINE FAILED — NOT pushing to git
    echo   Review the error above, fix, and re-run.
    echo ============================================================
    pause
    exit /b 1
)

REM --- 4. Stage model files -----------------------------------
echo.
echo [4/6] Staging trained model files...
git add models/
git add src/data/db/models.py 2>nul

REM --- 5. Commit (only if there are staged changes) -----------
echo.
echo [5/6] Committing...
git diff --staged --quiet
if errorlevel 1 (
    for /f "tokens=*" %%i in ('powershell -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%i
    git commit -m "Weekly retrain - !TODAY!"
    if errorlevel 1 (
        echo ERROR: git commit failed.
        pause
        exit /b 1
    )
) else (
    echo No model changes to commit (training produced identical artifacts).
)

REM --- 6. Push ------------------------------------------------
echo.
echo [6/6] Pushing to origin...
git push
if errorlevel 1 (
    echo.
    echo ERROR: git push failed. Check network / credentials.
    echo Commit is local; you can retry with: git push
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   PIPELINE COMPLETE — %DATE% %TIME%
echo   Render will auto-redeploy with the new models in ~3 min.
echo   Next training: next Friday 23:00 IST.
echo ============================================================
echo.
pause
endlocal
