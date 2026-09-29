"""Official Camera Transform（官方鏡頭轉換移植）.

逐行對應 docs/CAMERA_TRANSFORM_GROUND_TRUTH.md，數學完全一致。
輸入世界座標與鏡頭狀態。world_to_client 保留官方數學，y 從畫面底部起算。
Playwright 頁面座標 y 從頂部起算，另經 client_to_page 翻轉。
"""


def world_to_client(world_x, world_y, center_x, center_y, zoom,
                    viewport_w, viewport_h, dpr):
    """回 (client_x, client_y)。"""
    aspect = viewport_w / viewport_h
    view_x = (world_x - center_x) / zoom
    view_y = (world_y - center_y) * aspect / zoom
    zero_to_one_x = (view_x + 1.0) * (0.5 / dpr)
    zero_to_one_y = (view_y + 1.0) * (0.5 / dpr)
    return (zero_to_one_x * viewport_w, zero_to_one_y * viewport_h)


def client_to_page(client_x, client_y, canvas_height, canvas_left=0, canvas_top=0):
    """將遊戲由下往上的 client_y 轉為頁面由上往下的座標。"""
    return (client_x + canvas_left, canvas_height - client_y + canvas_top)


def world_to_page(world_x, world_y, center_x, center_y, zoom,
                  viewport_w, viewport_h, dpr, canvas_left=0, canvas_top=0):
    client_x, client_y = world_to_client(
        world_x, world_y, center_x, center_y, zoom, viewport_w, viewport_h, dpr)
    return client_to_page(client_x, client_y, viewport_h / dpr, canvas_left, canvas_top)
