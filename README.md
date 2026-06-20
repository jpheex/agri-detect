# 農業病蟲害辨識系統

上傳照片辨識植物種類與病蟲害，並結合 Gemini 多部位診斷與本地 IPM 知識庫。

## 快速開始

```bash
pip install -r requirements.txt
cp .env.example .env   # 填入 GEMINI_API_KEY
python -m uvicorn backend.main:app --reload
```

瀏覽 http://127.0.0.1:8000

## 版本號

- 格式：`v x.xxx`（例如 `v 1.005`）
- 修改專案根目錄 `VERSION` 後 push 即可發版

## 開發工具

```bash
pip install -r requirements-dev.txt
pre-commit install
pre-commit run --all-files
```

## 訓練資料版本控管（DVC）

見 [docs/DVC.md](docs/DVC.md)。

## 部署

Render Blueprint：`render.yaml`
