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

| 檔案 | 用途 |
|------|------|
| `render.yaml` | **免費預覽**：可試用，但重啟後資料全失 |
| `render.persistent.yaml` | **正式環境**：Starter + 1GB 磁碟，資料永久保留 |
| `docker-compose.yml` | 本機／自架，資料存在 Docker volume |
| **Cloudflare D1 + R2** | 免費額度內持久化，可搭配 Render 免費 Web | 見 [docs/CLOUDFLARE.md](docs/CLOUDFLARE.md) |

### 資料持久化（重要）

Render **免費方案**的磁碟是暫時性的：`data/app.db`（訓練、驗收、知識庫）、上傳照片、離線佇列在**重新部署或重啟後都會消失**。這不是程式 bug，是平台限制。

**正式累積訓練資料，請擇一：**

1. **Cloudflare D1 + R2（推薦搭配 Render 免費版）**
   資料庫與照片存 Cloudflare，Render 重啟不影響。設定見 [docs/CLOUDFLARE.md](docs/CLOUDFLARE.md)。

2. **Render 持久化磁碟**
   - 用 `render.persistent.yaml` 部署（需 Starter 方案，約 $7/月 + 磁碟）
   - 或在 Dashboard 將現有服務升級為 Starter，並掛載 Persistent Disk 至 `/opt/render/project/src/data`

3. **本機 Docker（推薦開發／自用）**
   ```bash
   docker compose up -d
   ```
   資料保存在 `agri_data` volume，重啟容器不會遺失。

4. **本機直接跑**
   ```bash
   python -m uvicorn backend.main:app --reload
   ```
   資料在專案 `data/` 目錄，只要不刪資料夾就會保留。

5. **DVC 備份訓練影像**
   見 [docs/DVC.md](docs/DVC.md)，可將標註影像版本控管到遠端，但**無法**自動還原線上驗收紀錄。

若使用暫時性部署，畫面頂部會顯示紅色警告橫幅。
