# Cloudflare D1 + R2 設定指南

訓練、驗收、知識庫與上傳照片可改存 **Cloudflare D1（SQL）** 與 **R2（物件儲存）**，Render 免費版重啟也不會遺失。

FastAPI 仍跑在 Render／本機；透過 API 連線 D1 與 R2（不需整個改寫成 Worker）。

## 1. 建立 Cloudflare 資源

```bash
npm install
npx wrangler login

# 建立 D1 資料庫（記下 database_id）
npm run cf:d1:create

# 建立 R2 bucket
npm run cf:r2:create

# 執行資料表 schema（遠端）
npm run cf:d1:migrate:remote
```

將 `wrangler.jsonc` 裡的 `REPLACE_WITH_D1_DATABASE_ID` 換成上一步的 ID。

## 2. 建立 R2 API Token

1. Cloudflare Dashboard → R2 → **Manage R2 API Tokens**
2. 權限：Object Read & Write，指定 bucket `agri-detect-media`
3. 記下 Access Key ID、Secret Access Key

**Endpoint** 格式：

```
https://<ACCOUNT_ID>.r2.cloudflarestorage.com
```

## 3. 建立 D1 API Token

1. [API Tokens](https://dash.cloudflare.com/profile/api-tokens) → Create Token
2. 範本：**Edit Cloudflare Workers** 或自訂權限含 **Account → D1 → Edit**
3. 記下 Token

**Account ID**：Dashboard 右側欄可見。

## 4. 環境變數

在 Render（或 `.env`）填入：

```env
# D1
CF_ACCOUNT_ID=你的_account_id
CF_API_TOKEN=你的_api_token
CF_D1_DATABASE_ID=你的_d1_database_uuid

# R2
R2_BUCKET_NAME=agri-detect-media
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
```

**D1 與 R2 都設定後**才會啟用雲端持久化；缺一則仍用本機 SQLite／`data/`。

## 5. 驗證

```bash
curl http://127.0.0.1:8000/api/health
```

應看到：

```json
"cloudflare": { "d1": true, "r2": true, "persistent": true },
"storage": { "persistent": true, "backend": "cloudflare_d1_r2" }
```

## 費用（概略）

| 服務 | 免費額度 |
|------|----------|
| D1 | 每日讀寫配額內免費（小專案通常夠用） |
| R2 | 10GB 儲存／月、Class A/B 操作免費額度 |

詳見 [Cloudflare 定價](https://developers.cloudflare.com/r2/pricing/)。

## 本機開發

不設上述變數時，自動使用 `data/app.db` + `data/uploads/`，與先前行為相同。

若要本機也連遠端 D1/R2 測試，把變數寫入 `.env` 即可。

## 從本機 SQLite 遷移（選用）

1. 匯出訓練清單：`GET /api/training/export`
2. 照片需手動上傳至 R2 或重新提交訓練樣本
3. 驗收紀錄可透過 SQL 匯入 D1（`schema/d1.sql` 結構相同）
