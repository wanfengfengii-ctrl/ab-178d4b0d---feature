"""API 冒烟脚本: 对运行中的服务发起真实 HTTP 请求。

由 verify.sh 在容器内启动 uvicorn 后调用; 任一步失败即以非零码退出。
默认目标 http://127.0.0.1:8000, 可用 BASE_URL 环境变量覆盖。
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def request(method: str, path: str, body: object = None) -> tuple[int, object]:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def check(condition: bool, message: str) -> None:
    if not condition:
        print(f"[SMOKE][FAIL] {message}")
        sys.exit(1)
    print(f"[SMOKE][OK]   {message}")


def wait_for_server(timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            status, _ = request("GET", "/healthz")
            if status == 200:
                return
        except Exception as exc:  # noqa: BLE001 - 启动期任何错误都重试
            last_error = exc
        time.sleep(0.4)
    print(f"[SMOKE][FAIL] 服务在 {timeout}s 内未就绪: {last_error}")
    sys.exit(1)


def main() -> None:
    print(f"[SMOKE] 目标服务: {BASE_URL}")
    wait_for_server()

    # 1) 健康检查
    status, data = request("GET", "/healthz")
    check(status == 200 and isinstance(data, dict) and data.get("status") == "ok",
          "GET /healthz 返回 200 且 status=ok")

    # 2) 前端静态产物由后端托管
    req = urllib.request.Request(f"{BASE_URL}/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        index_html = resp.read().decode()
    check(resp.status == 200 and 'id="root"' in index_html,
          "GET / 返回前端入口 index.html")

    # 3) UNIQUE 场景
    status, data = request("POST", "/api/reconstruct", {
        "target_length": 4,
        "fragments": [
            {"id": "A", "offset": 0, "payload": "1122", "weight": 10},
            {"id": "B", "offset": 2, "payload": "2233", "weight": 20},
        ],
    })
    check(status == 200, "UNIQUE 用例返回 200")
    assert isinstance(data, dict)
    check(data["status"] == "UNIQUE", "裁决为 UNIQUE")
    check(data["bodies"][0]["hex"] == "11222233", "正文十六进制为 11222233")
    check(data["optimal"]["total_weight"] == 30, "最大总权重为 30")
    check(data["optimal"]["fragment_count"] == 2, "最优片段数为 2")

    # 4) AMBIGUOUS 场景: 两份最优正文按无符号字节序
    status, data = request("POST", "/api/reconstruct", {
        "target_length": 1,
        "fragments": [
            {"id": "A", "offset": 0, "payload": "00", "weight": 5},
            {"id": "B", "offset": 0, "payload": "FF", "weight": 5},
        ],
    })
    check(status == 200, "AMBIGUOUS 用例返回 200")
    assert isinstance(data, dict)
    check(data["status"] == "AMBIGUOUS", "裁决为 AMBIGUOUS")
    check([b["hex"] for b in data["bodies"]] == ["00", "FF"],
          "两份正文按无符号字节序为 00 < FF 且附见证")

    # 5) IMPOSSIBLE / GAP
    status, data = request("POST", "/api/reconstruct", {
        "target_length": 3,
        "fragments": [
            {"id": "A", "offset": 0, "payload": "11", "weight": 1},
            {"id": "B", "offset": 2, "payload": "33", "weight": 1},
        ],
    })
    check(status == 200, "GAP 用例返回 200")
    assert isinstance(data, dict)
    check(data["status"] == "IMPOSSIBLE"
          and data["impossible_reason"] == "GAP", "裁决为 IMPOSSIBLE/GAP")
    check(data["uncovered_positions"] == [1], "缺口位置为 [1]")

    # 6) 非法输入 -> 422 且带字段位置
    status, data = request("POST", "/api/reconstruct", {
        "target_length": 2,
        "fragments": [
            {"id": "A", "offset": 0, "payload": "ZZ", "weight": 1},
            {"id": "A", "offset": 5, "payload": "00", "weight": 0},
        ],
    })
    check(status == 422, "非法输入返回 HTTP 422")
    assert isinstance(data, dict)
    locs = {tuple(e["loc"]): e for e in data["detail"]}
    check(("body", "fragments", 0, "payload") in locs,
          "422 定位到 fragments[0].payload")
    check(("body", "fragments", 1, "id") in locs,
          "422 定位到重复编号 fragments[1].id")
    check(("body", "fragments", 1, "weight") in locs,
          "422 定位到 fragments[1].weight")

    print("[SMOKE] 全部冒烟检查通过。")


if __name__ == "__main__":
    main()
