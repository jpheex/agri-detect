# DVC 訓練資料版本控管

本專案使用 [DVC](https://dvc.org/) 管理**訓練影像**等大型檔案，Git 只追蹤 `.dvc` 指標檔。

## 目錄約定

| 路徑 | 說明 | 版本控管 |
|------|------|----------|
| `data/training/` | 人工標註訓練影像 | DVC |
| `data/uploads/` | 使用者上傳（執行時） | 不納入 Git/DVC |
| `data/app.db` | SQLite 資料庫 | 不納入 Git |

## 首次設定（已完成 `dvc init`）

```bash
pip install -r requirements-dev.txt
dvc status
```

## 新增或更新訓練集

```bash
# 將影像放入 data/training/
dvc add data/training
git add data/training.dvc data/training/.gitignore .gitignore
git commit -m "更新訓練資料 v1.006"
```

## 還原特定版本

```bash
git checkout <commit> -- data/training.dvc
dvc checkout data/training.dvc
```

## 遠端儲存（選配）

目前 `.dvc/config` 使用本機 cache。若要團隊共享，可改用 S3 / Google Drive 等：

```bash
dvc remote add -d myremote s3://your-bucket/agri-detect
dvc push
```

## 與網站知識庫的關係

- 網站「預防訓練」會寫入 `data/app.db` 的 `knowledge_*` 表（執行時資料）
- DVC 管理的是**離線標註影像集**，供備份、再訓練或匯出，兩者互補
