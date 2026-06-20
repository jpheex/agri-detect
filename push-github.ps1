# 用法（先完成 GitHub 建 repo 後）：
#   powershell -ExecutionPolicy Bypass -File .\push-github.ps1 -RepoUrl "https://github.com/你的帳號/agri-detect.git"

param(
    [Parameter(Mandatory = $true)]
    [string]$RepoUrl
)

$git = "C:\Program Files\Git\bin\git.exe"
Set-Location $PSScriptRoot

& $git remote remove origin 2>$null
& $git remote add origin $RepoUrl
& $git push -u origin main

Write-Host ""
Write-Host "推送完成。下一步到 Render 部署：" -ForegroundColor Green
Write-Host "1. 開啟 https://dashboard.render.com/blueprints"
Write-Host "2. New Blueprint Instance -> 連 GitHub -> 選 agri-detect repo"
Write-Host "3. 設定 GEMINI_API_KEY 環境變數"
Write-Host "4. Deploy"
