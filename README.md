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

### 候选阶梯（可选，`ladder_size` 2–5）

复核员在得到上述裁决后，可要求生成 **2 至 5 级候选阶梯**，查看"当前高可信证据被否定时，
最接近的其他正文"。

- **计分**：对**每份不同正文**，取所有与它完全一致的片段作为见证（权重均为正，全取即唯一地
  同时最大化该正文的总权重与片段数），以 `(总权重, 片段数)` 作为该正文可达到的最大得分。
  同一份正文无论存在多少条重复/叠加覆盖，都只计为一个候选，不会重复占位。
- **排序**：得分降序；得分相同按**无符号字节序列**升序；返回前 N 份。
- **首差位置**：从第 2 阶起，每一阶标注与**上一阶**首次不同的字节偏移（0 起算）。
- **穷尽标记**：不同正文不足 N 份时 `exhausted=true` 且 `total_bodies` 给出精确正文总数；
  `IMPOSSIBLE`（GAP / CONFLICT）时阶梯为空，**绝不伪造候选**。
- **兼容**：请求不传 `ladder_size`（或传 `null`）时，请求与响应与旧契约完全一致——
  响应中不出现 `ladder` 字段。

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

#### 候选阶梯响应（请求带 `"ladder_size": 3`）

原响应字段全部保留，额外追加一个 `ladder` 对象：

```json
{
  "ladder": {
    "requested": 3,
    "total_bodies": 3,
    "exhausted": true,
    "rungs": [
      {
        "rank": 1,
        "hex": "00FF",
        "total_weight": 101,
        "fragment_count": 2,
        "witness_fragment_ids": ["X", "Z"],
        "adopted_fragments": [ ... ],
        "first_diff_position": null,
        "is_optimal": true
      },
      {
        "rank": 2,
        "hex": "01FF",
        "total_weight": 101,
        "fragment_count": 2,
        "witness_fragment_ids": ["Y", "Z"],
        "adopted_fragments": [ ... ],
        "first_diff_position": 0,
        "is_optimal": true
      }
    ]
  }
}
```

`ladder_size` 必须是 2–5 的整数（`null` 等同缺省），越界同样返回 422，
错误定位在 `["body","ladder_size"]`。

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

1. `pytest`：求解器与 API 共 53 项测试，覆盖高权片段互斥、等分正文、缺口、冲突致不可行、
   等权双正文的无符号字节序、同权重按片段数决胜、非法输入 422 与字段定位，以及候选阶梯的
   得分排序、同正文重复覆盖去重、首差位置、穷尽标记、IMPOSSIBLE 不伪造与向后兼容；
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
- **候选阶梯**：输入区勾选"生成候选阶梯"并选择 2–5 级后提交，阶梯在原裁决区展开：
  每阶一张选项卡（得分、片段数、正文前缀，★ 标记与裁决同分的最优正文），切换选项卡时
  **联动既有十六进制视图与片段悬停高亮**，琥珀描边标出该阶与上一阶首次不同的字节；
  正文不足 N 份时明确提示已穷尽。任一输入或阶梯数量改变都会**立即撤下旧结果**。
- **冲突与缺口扫描栅格**：逐字节标注冲突（琥珀）与缺口（红），点击冲突格查看各片段主张的字节，
  使"片段冲突"与"正文歧义"清晰可分。

## 7. 求解算法

`backend/solver.py` 将片段建模为**冲突图**上的带权独立集 + 覆盖约束：

- 两片段区间相交且存在字节分歧则连冲突边（不可同时采用）；
- 每个片段对应一个区间覆盖位掩码（目标 ≤ 512 字节，用 Python 大整数表示）；
- DFS 按"偏移升序、权重降序"分支，含分支做包含/排除搜索；
- 剪枝：若剩余所有相容片段全取后仍无法补全覆盖，或权重/计数上界不优于当前最优，立即回溯；
- 找到最优解后按正文内容归并，区分 UNIQUE / AMBIGUOUS，并以字节字典序（等价无符号字节序）取最小两份。

候选阶梯则**直接按不同正文枚举**而非覆盖组合：逐位置从"仍与已确定前缀一致的存活片段"
所主张的字节中取值，分歧位置才展开决策；维护每位置存活覆盖计数，任何位置失盖立即回溯，
因此不会产生"逐字节选得出、却无一致片段集能完整覆盖"的伪正文。每份不同正文只产生一个叶子
（天然免疫同正文重复覆盖占位），其存活片段集就是该正文唯一的最大见证。28 片段下不同正文
数量上界约 2¹⁴，全量枚举为亚秒级。

求解器已通过 300 组随机小实例与暴力枚举的交叉验证（零分歧），28 片段对抗实例在毫秒级完成。
