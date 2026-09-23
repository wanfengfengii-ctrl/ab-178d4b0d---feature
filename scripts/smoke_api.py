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

    # 7) 未启用阶梯时响应不含 ladder 字段(向后兼容)
    status, data = request("POST", "/api/reconstruct", {
        "target_length": 2,
        "fragments": [
            {"id": "A", "offset": 0, "payload": "00", "weight": 10},
            {"id": "B", "offset": 1, "payload": "FF", "weight": 10},
        ],
    })
    check(status == 200, "兼容请求返回 200")
    assert isinstance(data, dict)
    check("ladder" not in data, "未传 ladder_size 时响应不含 ladder 字段")

    # 8) 候选阶梯: 得分降序 + 同分无符号序 + 首差位置 + 去重
    status, data = request("POST", "/api/reconstruct", {
        "target_length": 1,
        "ladder_size": 3,
        "fragments": [
            {"id": "X0", "offset": 0, "payload": "00", "weight": 100},
            {"id": "X1", "offset": 0, "payload": "01", "weight": 60},
            {"id": "X2", "offset": 0, "payload": "02", "weight": 10},
        ],
    })
    check(status == 200, "阶梯请求返回 200")
    assert isinstance(data, dict)
    ladder = data.get("ladder")
    check(isinstance(ladder, dict), "响应包含 ladder")
    rungs = ladder["rungs"]
    check([r["hex"] for r in rungs] == ["00", "01", "02"],
          "阶梯按总权重降序返回 00/01/02")
    check([r["total_weight"] for r in rungs] == [100, 60, 10],
          "各阶给出该正文可达到的最大总权重")
    check(rungs[0]["first_diff_position"] is None
          and rungs[1]["first_diff_position"] == 0
          and rungs[2]["first_diff_position"] == 0,
          "首阶无首差, 其余标明与上一阶首次不同的字节位置")
    check(ladder["total_bodies"] == 3 and ladder["exhausted"] is True,
          "仅 3 份正文时明确标记已穷尽")

    # 9) 同正文重复覆盖不得占用多个阶梯名次
    dup_frags = []
    for body_byte in (0x00, 0x01):
        for dup in range(10):
            dup_frags.append({
                "id": f"B{body_byte:02X}-{dup}",
                "offset": 0,
                "payload": f"{body_byte:02X}",
                "weight": 1,
            })
    status, data = request("POST", "/api/reconstruct", {
        "target_length": 1,
        "ladder_size": 5,
        "fragments": dup_frags,
    })
    check(status == 200, "重复覆盖阶梯请求返回 200")
    assert isinstance(data, dict)
    check([r["hex"] for r in data["ladder"]["rungs"]] == ["00", "01"],
          "20 条同正文重复覆盖只产生 2 个阶梯名次")
    check(all(r["fragment_count"] == 10 for r in data["ladder"]["rungs"]),
          "每份正文取其全部一致片段作为见证(10 片)")

    # 10) IMPOSSIBLE 不伪造候选
    status, data = request("POST", "/api/reconstruct", {
        "target_length": 3,
        "ladder_size": 5,
        "fragments": [
            {"id": "A", "offset": 0, "payload": "11", "weight": 1},
            {"id": "B", "offset": 2, "payload": "33", "weight": 1},
        ],
    })
    check(status == 200, "IMPOSSIBLE 阶梯请求返回 200")
    assert isinstance(data, dict)
    check(data["ladder"]["rungs"] == [] and data["ladder"]["total_bodies"] == 0,
          "IMPOSSIBLE 时阶梯为空, 不伪造候选正文")

    # 11) ladder_size 越界 -> 422 且定位到 ladder_size
    status, data = request("POST", "/api/reconstruct", {
        "target_length": 1,
        "ladder_size": 9,
        "fragments": [
            {"id": "A", "offset": 0, "payload": "00", "weight": 1},
            {"id": "B", "offset": 0, "payload": "00", "weight": 1},
        ],
    })
    check(status == 422, "ladder_size=9 返回 422")
    assert isinstance(data, dict)
    check(tuple(data["detail"][0]["loc"]) == ("body", "ladder_size"),
          "422 定位到 ladder_size")

    print("[SMOKE] 全部冒烟检查通过。")


if __name__ == "__main__":
    main()
