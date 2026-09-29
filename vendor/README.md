# vendor（第三方參考原始碼）使用規則

- `vendor/kiomet-ref/` = 官方公開 Kiomet 原始碼（SoftbearStudios/kiomet，
  AGPL-3.0），僅作唯讀參考（輸入語意、設定、規則理解）。
- 絕對禁止把 AGPL 程式碼複製進 `src/`（避免授權污染）。
- 絕對禁止用開源客戶端連官方伺服器（官方明令禁止，避免視野作弊疑慮）。
- `vendor/` 不進 Git 版控（見根目錄 `.gitignore`），每台機器按需取得。
- 取得方式：`git clone --depth 1 --filter=blob:none --sparse <url>
  vendor/kiomet-ref` 後 `sparse-checkout set client common`。
