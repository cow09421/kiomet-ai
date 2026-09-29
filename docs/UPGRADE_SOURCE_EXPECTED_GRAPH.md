# 升級來源預期圖（2026-09-28）

由 `tools/extract_upgrade_graph.py` 自公開來源靜態抽取：
`vendor/kiomet-ref/common/src/tower.rs` 的 `TowerType`
`prerequisite` 屬性。首 token 為降級源，其餘為額外前置需求。

機器可讀：`runtime/research/upgrade/source_expected_graph.json`
Production 對照：`runtime/research/upgrade/source_vs_production.json`

## 邊一覽（19 條，全 SOURCE_EXPECTED）

| 來源 | 目標 | 額外前置 | Production 狀態 |
| --- | --- | --- | --- |
| Runway（跑道） | Airfield（機場） | Factory 2、Radar 1 | SOURCE_MATCH |
| Barracks（兵營） | Armory（軍械庫） | Factory 1、Mine 1 | UI_UNKNOWN |
| Bunker（碉堡） | Artillery（砲兵陣地） | Refinery 2、Radar 3 | UI_UNKNOWN |
| Mine（礦場） | Bunker（碉堡） | Headquarters 1、Ews 1 | SOURCE_MATCH |
| Factory（工廠） | Centrifuge（離心機） | Mine 3 | UI_UNKNOWN |
| Town（城鎮） | City（都市） | Quarry 2、Reactor 1、Town 3 | UI_UNKNOWN |
| Radar（雷達） | Ews（預警系統） | Generator 2 | UI_UNKNOWN |
| Village（村莊） | Headquarters（總部） | Radar 1 | SOURCE_MATCH |
| Airfield（機場） | Helipad（直升機坪） | Armory 2、Factory 3 | UI_UNKNOWN |
| Rocket（火箭） | Launcher（發射器） | Airfield 2 | UI_UNKNOWN |
| Centrifuge（離心機） | Projector（投射器） | Rampart 2、Reactor 2 | UI_UNKNOWN |
| Cliff（懸崖） | Quarry（採石場） | Village 1 | UI_UNKNOWN |
| Cliff（懸崖） | Rampart（壁壘） | Barracks 2 | UI_UNKNOWN |
| Generator（發電機） | Reactor（反應爐） | Centrifuge 1 | SOURCE_MATCH |
| Factory（工廠） | Refinery（精煉廠） | Generator 3、Cliff 1 | UI_UNKNOWN |
| Radar（雷達） | Rocket（火箭） | Refinery 1 | UI_UNKNOWN |
| Ews（預警系統） | Satellite（衛星） | Rocket 2、Generator 5 | UI_UNKNOWN |
| Quarry（採石場） | Silo（飛彈井） | Centrifuge 2 | UI_UNKNOWN |
| Village（村莊） | Town（城鎮） | Generator 1、Village 3 | SOURCE_MATCH |

## 語意說明

- 每條邊的「額外前置」在 Production UI 以「X=have/need」列顯示
  （如 Airfield 需 Factory=2、Radar=1，UI 顯示 工廠=0/2、雷達=0/1）。
- UI 的 N/M 前置列不是兵力（見 `src/kiomet_ai/ui_parse.py` 分流規則）。
- 發現 Source／Production 不一致時標 PRODUCTION_DELTA，
  不修 Source、不硬套（目前 0 差異）。
