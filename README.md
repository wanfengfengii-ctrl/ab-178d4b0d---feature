# 档案片段重建台（Archive Fragment Reconstruction Console）

面向档案复核员的字节片段重建工具：导入或编辑带有重叠的十六进制字节片段，
由业务 API 计算可能的原文，页面展示**正文十六进制、采用的片段见证与冲突位置**。

- 前端：TypeScript + React 18 + Vite
- 后端：Python 3.11 + FastAPI（生产镜像中由 FastAPI 静态托管前端产物）
- 部署：多阶段 `Dockerfile` + 带健康检查的 `docker-compose.yml`，宿主机端口可通过 `HOST_PORT` 配置
- 验收：`verify` 一次性服务依次执行 **pytest 代码测试 → 前端构建 → API 冒烟**，自行退出并以退出码报告结果

---

## 1. 数据模型与业务规则

目标正文长度 `target_length` ∈ [1, 512] 字节；片段数 ∈ [2, 28]。

每个片段包含：

| 字段 | 约束 |
| --- | --- |
| `id` | 非空字符串，全局唯一 |
| `offset` | 从零起算的整数，不能为负 |
| `payload` | 非空、偶数长度的十六进制字符串（仅 `0-9 a-f A-F`） |
| `weight` | 整数可信权重，1 至 1,000,000 |

**有效方案**：选出的片段两两在重叠位置字节完全相同（一致覆盖），且其并集覆盖 `[0, target_length)` 的**每一个**字节。

**择优（字典序目标）**：

1. 最大化采用片段的**总权重**；
2. 总权重相同时，最大化采用**片段数**。

API 返回这两个最优值（`optimal.total_weight` / `optimal.fragment_count`）。

**裁决**：

- `UNIQUE` — 所有最优方案还原同一份正文，返回该正文（十六进制大写）与片段见证；
- `AMBIGUOUS` — 最优方案可还原多种正文，按**无符号字节序列**给出最小的两份（rank 1/2），并分别列出各自动员的片段见证；
- `IMPOSSIBLE` — 不存在完整一致的覆盖。`impossible_reason` 区分：
  - `GAP`：存在任何片段都覆盖不到的目标字节（返回具体位置 `uncovered_positions`）；
  - `CONFLICT`：每个字节虽有覆盖，但无法选出一组互不矛盾的片段完成全覆盖。

> 输入层的**片段冲突**（证据互相矛盾的位置）与裁决结果的**正文歧义**（不同最优方案还原不同正文）是两个独立概念：
> 例如高权片段互斥但一边占优时，存在冲突位置却裁决 UNIQUE；页面会同时展示两者，帮助复核员区分。

## 2. HTTP API

### `POST /api/reconstruct`

请求：

```json
{
  "target_length": 4,
  "fragments": [
    {"id": "A", "offset": 0, "payload": "1122", "weight": 10},
    {"id": "B", "offset": 2, "payload": "2233", "weight": 20}
  ]
}
```

成功响应（节选）：

```json
{
  "status": "UNIQUE",
  "target_length": 4,
  "optimal": {"total_weight": 30, "fragment_count": 2},
  "bodies": [
    {
      "rank": 1,
      "hex": "11222233",
      "witness_fragment_ids": ["A", "B"],
      "adopted_fragments": [
        {"id": "A", "offset": 0, "payload": "1122", "weight": 10},
        {"id": "B", "offset": 2, "payload": "2233", "weight": 20}
      ]
    }
  ],
  "conflicts": [],
  "conflict_positions": [],
  "uncovered_positions": [],
  "impossible_reason": null
}
```

### 错误响应（HTTP 422）

重复编号、十六进制格式错、越界等一律返回 422，并在 `detail[].loc` 给出**字段位置**：

```json
{
  "detail": [
    {"loc": ["body", "fragments", 0, "payload"], "msg": "含有非十六进制字符…", "type": "value_error.hex"},
    {"loc": ["body", "fragments", 1, "id"], "msg": "编号重复: 'A' 首次出现于 fragments[0]", "type": "value_error.duplicate"},
    {"loc": ["body", "fragments", 1, "offset"], "msg": "片段越界: …", "type": "value_error.bounds"}
  ]
}
```

其他端点：`GET /healthz`（容器健康检查）、`GET /api/health`。

## 3. 本地开发

```bash
# 后端
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000

# 前端(另开终端; /api 与 /healthz 自动代理到 :8000)
cd frontend
npm install
npm run dev
```

## 4. Docker 部署

```bash
# 宿主机端口默认 8080; 可自行配置
HOST_PORT=9000 docker compose up -d --build web
# 打开 http://localhost:9000
docker compose ps        # 查看健康状态 (healthy)
```

`web` 服务内置 Docker `HEALTHCHECK` 与 compose `healthcheck`，探测 `/healthz`。

## 5. verify 一次性验收服务

`verify` 是**一次性**服务（非守护）：构建后运行测试、前端构建与 API 冒烟，
全部通过退出码 `0`，任一步失败立即非零退出。

```bash
docker compose --profile verify build verify
docker compose --profile verify run --rm verify
echo "exit code = $?"   # 0 表示全部通过
```

容器内执行的三步与本地一致：

1. `pytest`：求解器与 API 共 32 项测试，覆盖高权片段互斥、等分正文、缺口、冲突致不可行、
   等权双正文的无符号字节序、同权重按片段数决胜、非法输入 422 与字段定位；
2. `npm run build`：TypeScript 严格类型检查 + Vite 生产构建；
3. `scripts/smoke_api.py`：容器内启动真实 uvicorn，发起 HTTP 冒烟（健康检查、静态首页、
   UNIQUE / AMBIGUOUS / IMPOSSIBLE 与 422 字段定位）。

本地也可直接运行：

```bash
APP_DIR=$PWD bash scripts/verify.sh
```

## 6. 前端复核视图

- **输入区**：内联编辑编号/偏移/载荷/权重（2–28 行），或"导入 JSON"批量导入；
  字段级红框即时提示；样例芯片一键载入（等分正文 / 高权互斥 / 正文歧义 / 缺口 / 冲突致不可行）。
- **修改即失效**：任何输入改动都会立即撤下旧裁决并显示提示，必须重新提交——避免新输入配旧结论。
- **正文十六进制视图**：每行 16 字节，带偏移与 ASCII 列；悬停见证片段高亮其覆盖区间，
  绿色底色标出多片段一致重叠位置。
- **裁决横幅**：绿（UNIQUE）/ 琥珀（AMBIGUOUS）/ 红（IMPOSSIBLE），并附最大总权重与最优片段数。
- **歧义对照**：AMBIGUOUS 时并列展示字节序最小的两份正文、首个差异偏移，以及各自片段见证。
- **冲突与缺口扫描栅格**：逐字节标注冲突（琥珀）与缺口（红），点击冲突格查看各片段主张的字节，
  使"片段冲突"与"正文歧义"清晰可分。

## 7. 求解算法

`backend/solver.py` 将片段建模为**冲突图**上的带权独立集 + 覆盖约束：

- 两片段区间相交且存在字节分歧则连冲突边（不可同时采用）；
- 每个片段对应一个区间覆盖位掩码（目标 ≤ 512 字节，用 Python 大整数表示）；
- DFS 按"偏移升序、权重降序"分支，含分支做包含/排除搜索；
- 剪枝：若剩余所有相容片段全取后仍无法补全覆盖，或权重/计数上界不优于当前最优，立即回溯；
- 找到最优解后按正文内容归并，区分 UNIQUE / AMBIGUOUS，并以字节字典序（等价无符号字节序）取最小两份。

求解器已通过 300 组随机小实例与暴力枚举的交叉验证（零分歧），28 片段对抗实例在毫秒级完成。
