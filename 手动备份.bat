@echo off
title 乡村振兴知识库 - 手动备份
cd /d "%~dp0"
chcp 65001 >nul
echo.
echo   ========================================
echo   乡村振兴知识库 - 手动备份
echo   ========================================
echo.

set TIMESTAMP=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%
set TIMESTAMP=%TIMESTAMP: =0%
set BACKUP_DIR=data\backup\%TIMESTAMP%

if not exist "data\backup" mkdir "data\backup"
mkdir "%BACKUP_DIR%"

echo   正在备份数据库...
if exist "data\database\knowledge_base.db" (
    copy "data\database\knowledge_base.db" "%BACKUP_DIR%\knowledge_base.db" >nul
    echo   [OK] 数据库已备份
) else (
    echo   [跳过] 数据库文件不存在
)

echo   正在备份配置文件...
if exist "config\settings.json" (
    copy "config\settings.json" "%BACKUP_DIR%\settings.json" >nul
    echo   [OK] 配置文件已备份
) else (
    echo   [跳过] 配置文件不存在
)

echo.
echo   ========================================
echo   备份完成! 保存在: %BACKUP_DIR%
echo   ========================================
pause
