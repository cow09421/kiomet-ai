# DEPLOY_FORCE SOURCE CALLCHAIN（語意命令源呼叫鏈）

> 用途：二進位映射的目標清單，不是終點。來源：公開原始碼唯讀追蹤
> （`vendor/kiomet-ref`＋`vendor/kodiak-ref`），未複製程式碼。

## 真人拖曳 → 語意命令（kiomet client `game.rs`）

```
MouseUp（左鍵放開，不同塔）
→ Drag::zip → (start, current)
→ World::find_best_path(start, current, max_edge_distance, player_id, is_visible)
→ Some(path) → Command::deploy_force_from_path(path)
→ context.send_to_game(Command)
```

關鍵語意（`common/src/world.rs:300`）：
`find_best_path`＝直接 `[src, dst]`（距離內）或 A*（≥2 跳）；
`find_best_incomplete_path` 只畫畫；放開要 complete。

## Command 構造（`common/src/protocol.rs`）

```
Command::deploy_force_from_path(path: Vec<TowerId>)
→ Command::DeployForce { tower_id: path[0], path: Path::new(path) }
```

## 發送邊界（kodiak `client_context.rs:559`）

```
ClientContext::send_to_game(request: GameRequest)
→ send_to_game_with_reliable(request, reliable=true)
→ send_to_server_with_reliable(CommonRequest::Game(request, game_fence), true)
→ self.socket.send(request, reliable)        ← Client Command Boundary
→ ReconnSocket::send → ProtoSocket::send
→ WebSocket::send / WebTransport::send
→ send_buf → encode_buffer（bitcode＋壓縮）→ transport
```

`GameRequest = Command`（kiomet `game.rs`），`fence` 為遊戲柵欄計數。

## 映射目標（給 matcher／instrumentation）

| # | Source 函式 | 層 | 狀態 |
|---|---|---|---|
| A | `World::find_best_path` | common | 待映射 |
| B | `Command::deploy_force_from_path` | common | 可能 inline，待確認 |
| C | `Command::DeployForce`（enum 構造） | common | 待映射 |
| D | `ClientContext::send_to_game` | kodiak | 待映射 |
| E | `GameRequest = Command`（型別） | kiomet | 型別別名，無本體 |
| F | `ReconnSocket::send`／`ProtoSocket::send` | kodiak | 待映射 |
| G | bitcode `Encode`（Command） | kodiak_common | 待映射 |
| H | `send_buf`／transport enqueue | kodiak net | 待映射 |

## 戰略含義

Server 只處理 `Command`（tower_id＋path），不需要滑鼠軌跡。
AI Executor 應打 `send_to_game` 級入口（官方路徑），而非像素拖曳。
下一步：A～H 映射到 Local WASM index，再到 Production candidate。
