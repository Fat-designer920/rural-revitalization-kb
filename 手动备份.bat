@echo off
title 乡村振兴知识库 - 备份
cd /d "%~dp0"
if exist "python\python.exe" (set PYTHON_CMD=python\python.exe) else (set PYTHON_CMD=python)
echo   正在备份数据库...
if not exist "backups" mkdir backups
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
%PYTHON_CMD% -c "import json,shutil,datetime;c=json.load(open(chr(99)+chr(111)+chr(110)+chr(102)+chr(105)+chr(103)+chr(47)+chr(115)+chr(101)+chr(116)+chr(116)+chr(105)+chr(110)+chr(103)+chr(115)+chr(46)+chr(106)+chr(115)+chr(111)+chr(110),r,encoding=utf-8));db=c.get(database_path,data/database/knowledge_base.db);ts=datetime.datetime.now().strftime(%%Y%%m%%d_%%H%%M%%S);dst=fbackups/kb_{ts}.db;shutil.copy2(db,dst);print(fOK:
