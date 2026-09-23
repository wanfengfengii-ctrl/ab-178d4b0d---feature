"""求解器单元测试, 对应用户验收的四类场景。"""

from __future__ import annotations

from backend.solver import Fragment, solve


def f(fid: str, offset: int, payload: str, weight: int) -> Fragment:
    return Fragment(id=fid, offset=offset, payload=bytes.fromhex(payload), weight=weight)


# ---------- 等分正文: 无争议覆盖, UNIQUE ----------

def test_even_split_body_is_unique():
    # 目标 6 字节, 两片段在偏移 3 处重叠且内容相同。
    frags = [
        f("A", 0, "AABBCCDD", 10),
        f("B", 3, "DDEEFF", 10),
    ]
    r = solve(6, frags)
    assert r.status == "UNIQUE"
    assert r.total_weight == 20
    assert r.fragment_count == 2
    assert r.bodies[0].hex == "AABBCCDDEEFF"
    assert set(r.bodies[0].witness_fragment_ids) == {"A", "B"}
    assert r.conflict_positions == ()
    assert r.uncovered_positions == ()


# ---------- 高权片段互斥 ----------

def test_mutually_exclusive_high_weight_picks_consistent_winner():
    # X(00..) 与 Y(01..) 在字节 0 互斥; X 权重更高, Z 补上字节 1。
    frags = [
        f("X", 0, "00", 1000),
        f("Y", 0, "01", 999),
        f("Z", 1, "FF", 1),
    ]
    r = solve(2, frags)
    assert r.status == "UNIQUE"
    assert r.total_weight == 1001
    assert set(r.bodies[0].witness_fragment_ids) == {"X", "Z"}
    assert r.bodies[0].hex == "00FF"
    # 输入层冲突位置仍需向复核员标出。
    assert r.conflict_positions == (0,)


def test_combined_low_weight_can_beat_single_high_weight():
    # 高权片段 A 与两条低权片段 B/C 互斥, 但 B+C 总权重更高。
    frags = [
        f("A", 0, "AABB", 60),
        f("B", 0, "CC", 50),
        f("C", 1, "DD", 50),
    ]
    r = solve(2, frags)
    assert r.status == "UNIQUE"
    assert r.total_weight == 100
    assert r.bodies[0].hex == "CCDD"
    assert set(r.bodies[0].witness_fragment_ids) == {"B", "C"}


def test_weight_tie_broken_by_fragment_count():
    # 正文 FFFFFFFF 只能靠 A(权重 100, 1 片); 正文 00000000 靠 B+C(总权重 100, 2 片)。
    # 总权重持平, 按片段数择优 -> B+C 的正文, 裁决 UNIQUE。
    frags = [
        f("A", 0, "FFFFFFFF", 100),
        f("B", 0, "0000", 50),
        f("C", 2, "0000", 50),
    ]
    r = solve(4, frags)
    assert r.status == "UNIQUE"
    assert (r.total_weight, r.fragment_count) == (100, 2)
    assert r.bodies[0].hex == "00000000"
    assert set(r.bodies[0].witness_fragment_ids) == {"B", "C"}


# ---------- 缺口 ----------

def test_gap_yields_impossible_with_positions():
    frags = [
        f("A", 0, "0011", 10),  # 覆盖 0,1
        f("B", 3, "33", 10),    # 覆盖 3
    ]
    r = solve(4, frags)
    assert r.status == "IMPOSSIBLE"
    assert r.impossible_reason == "GAP"
    assert r.uncovered_positions == (2,)
    assert r.total_weight is None
    assert r.bodies == ()


def test_forced_conflict_without_gap_yields_impossible():
    # 字节 0 只有 A 能盖, 字节 2 只有 B 能盖, 二者在字节 1 必冲突。
    frags = [
        f("A", 0, "0000", 10),  # [0,1] = 00 00
        f("B", 1, "0101", 10),  # [1,2] = 01 01
    ]
    r = solve(3, frags)
    assert r.status == "IMPOSSIBLE"
    assert r.impossible_reason == "CONFLICT"
    assert r.uncovered_positions == ()
    assert r.conflict_positions == (1,)


# ---------- 正文歧义 ----------

def test_ambiguous_returns_two_smallest_bodies_unsigned_order():
    # 字节 0 有两个等权互斥选项, 字节 1 固定 -> 两个最优正文。
    frags = [
        f("X", 0, "00", 100),
        f("Y", 0, "01", 100),
        f("Z", 1, "FF", 1),
    ]
    r = solve(2, frags)
    assert r.status == "AMBIGUOUS"
    assert r.total_weight == 101
    assert r.fragment_count == 2
    assert len(r.bodies) == 2
    assert r.bodies[0].hex == "00FF"
    assert set(r.bodies[0].witness_fragment_ids) == {"X", "Z"}
    assert r.bodies[1].hex == "01FF"
    assert set(r.bodies[1].witness_fragment_ids) == {"Y", "Z"}


def test_ambiguous_only_returns_two_smallest_of_three():
    frags = [
        f("X0", 0, "00", 10),
        f("X1", 0, "01", 10),
        f("X2", 0, "02", 10),
        f("Z", 1, "FF", 1),
    ]
    r = solve(2, frags)
    assert r.status == "AMBIGUOUS"
    assert [b.hex for b in r.bodies] == ["00FF", "01FF"]


def test_unsigned_byte_ordering_above_127():
    # 7F.. 与 80.. 必须按无符号字节排序: 0x7F < 0x80。
    frags = [
        f("HI", 0, "80", 5),
        f("LO", 0, "7F", 5),
    ]
    r = solve(1, frags)
    assert r.status == "AMBIGUOUS"
    assert r.bodies[0].hex == "7F"
    assert r.bodies[1].hex == "80"


def test_consistent_fragments_all_stack_into_optimal():
    # 权重均为正: 互相一致的片段总会被全部采用(叠加只增不减总权重)。
    frags = [
        f("P", 0, "AABB", 7),
        f("Q", 0, "AA", 4),
        f("R", 1, "BB", 3),
    ]
    r = solve(2, frags)
    assert r.status == "UNIQUE"
    assert (r.total_weight, r.fragment_count) == (14, 3)
    assert r.bodies[0].hex == "AABB"
    assert set(r.bodies[0].witness_fragment_ids) == {"P", "Q", "R"}


def test_agreeing_overlap_is_not_conflict():
    frags = [
        f("A", 0, "112233", 5),
        f("B", 2, "3344", 5),
    ]
    r = solve(4, frags)
    assert r.status == "UNIQUE"
    assert r.conflict_positions == ()
    assert r.bodies[0].hex == "11223344"


def test_28_fragments_performance():
    # 14 个位置, 每个位置两个等权单字节候选 -> 2^14 个最优解, 需快速完成。
    frags = []
    for i in range(14):
        frags.append(f(f"lo{i}", i, "00", 1))
        frags.append(f(f"hi{i}", i, "01", 1))
    r = solve(14, frags)
    assert r.status == "AMBIGUOUS"
    assert r.total_weight == 14
    assert r.fragment_count == 14
    assert r.bodies[0].hex == "00" * 14
    assert r.bodies[1].hex == "00" * 13 + "01"


# ---------- 候选阶梯 ----------

def test_ladder_absent_when_not_requested():
    # 未启用时结果对象与序列化输出都必须与旧契约兼容。
    r = solve(2, [f("A", 0, "0011", 10), f("B", 0, "0011", 20)])
    assert r.ladder is None
    assert "ladder" not in r.to_dict()


def test_ladder_rung_one_matches_verdict():
    frags = [
        f("X", 0, "00", 100),
        f("Y", 0, "01", 100),
        f("Z", 1, "FF", 1),
    ]
    r = solve(2, frags, 5)
    assert r.ladder is not None
    assert r.ladder.requested == 5
    assert r.ladder.total_bodies == 2
    assert r.ladder.exhausted is True  # 只有 2 份不同正文, 不足 5 -> 已穷尽
    rungs = r.ladder.rungs
    assert [x.hex for x in rungs] == ["00FF", "01FF"]
    # 首阶与裁决正文逐字段一致。
    assert rungs[0].hex == r.bodies[0].hex
    assert rungs[0].total_weight == r.total_weight
    assert rungs[0].fragment_count == r.fragment_count
    assert set(rungs[0].witness_fragment_ids) == {"X", "Z"}
    assert rungs[0].first_diff_position is None
    assert rungs[0].is_optimal is True
    # 次阶标明与上一阶首次不同的字节位置。
    assert rungs[1].first_diff_position == 0
    assert set(rungs[1].witness_fragment_ids) == {"Y", "Z"}


def test_ladder_ranked_by_score_then_unsigned_body():
    # 首字节 00 路径权重最高; 02 次之; 01 最低 —— 排序只看得分, 不看字节序。
    frags = [
        f("A", 0, "00", 100),
        f("B", 0, "01", 10),
        f("C", 0, "02", 60),
        f("Z", 1, "FF", 1),
    ]
    r = solve(2, frags, 5)
    rungs = r.ladder.rungs
    assert [x.hex for x in rungs] == ["00FF", "02FF", "01FF"]
    assert [x.total_weight for x in rungs] == [101, 61, 11]
    assert [x.first_diff_position for x in rungs] == [None, 0, 0]
    assert rungs[0].is_optimal is True
    assert all(x.is_optimal is False for x in rungs[1:])
    assert r.ladder.exhausted is True


def test_ladder_tie_score_orders_by_unsigned_bytes():
    frags = [
        f("HI", 0, "80", 5),
        f("LO", 0, "7F", 5),
    ]
    r = solve(1, frags, 2)
    assert [x.hex for x in r.ladder.rungs] == ["7F", "80"]
    assert all(x.is_optimal for x in r.ladder.rungs)


def test_ladder_top_n_truncation_and_exhausted_flag():
    frags = [
        f("X0", 0, "00", 10),
        f("X1", 0, "01", 10),
        f("X2", 0, "02", 10),
        f("Z", 1, "FF", 1),
    ]
    r = solve(2, frags, 2)
    assert len(r.ladder.rungs) == 2
    assert [x.hex for x in r.ladder.rungs] == ["00FF", "01FF"]
    assert r.ladder.total_bodies == 3  # 总数仍精确给出
    assert r.ladder.exhausted is False


def test_ladder_same_body_duplicate_covers_dedup():
    # 三份不同正文, 每份由 8 条内容完全相同的重复片段见证 -> 28 片段里大量同正文
    # 重复覆盖; 阶梯必须按不同正文去重, 不能让同一正文占多个名次。
    frags = []
    for body_idx, (byte, weight) in enumerate(
        [(0x00, 3), (0x01, 2), (0x02, 1)]
    ):
        for dup in range(8):
            frags.append(f(f"B{body_idx}-{dup}", 0, f"{byte:02X}" * 4, weight))
    assert len(frags) == 24
    r = solve(4, frags, 5)
    assert r.ladder.total_bodies == 3
    assert [x.hex for x in r.ladder.rungs] == [
        "00" * 4,
        "01" * 4,
        "02" * 4,
    ]
    assert all(x.fragment_count == 8 for x in r.ladder.rungs)
    assert [x.total_weight for x in r.ladder.rungs] == [24, 16, 8]
    assert r.ladder.exhausted is True


def test_ladder_witness_is_all_consistent_fragments():
    # 与正文一致的额外片段(权重为正)必须全部纳入见证, 以最大化该正文得分。
    frags = [
        f("X", 0, "00", 100),
        f("Y", 0, "01", 100),
        f("Z", 1, "FF", 1),
        f("Q", 1, "FF", 7),
    ]
    r = solve(2, frags, 2)
    rung0 = r.ladder.rungs[0]
    assert set(rung0.witness_fragment_ids) == {"X", "Z", "Q"}
    assert rung0.total_weight == 108
    assert rung0.fragment_count == 3
    assert set(r.ladder.rungs[1].witness_fragment_ids) == {"Y", "Z", "Q"}


def test_ladder_impossible_conflict_forges_nothing():
    frags = [
        f("A", 0, "0000", 10),
        f("B", 1, "0101", 10),
    ]
    r = solve(3, frags, 5)
    assert r.status == "IMPOSSIBLE"
    assert r.ladder.rungs == ()
    assert r.ladder.total_bodies == 0
    assert r.ladder.exhausted is True


def test_ladder_impossible_gap_forges_nothing():
    frags = [
        f("A", 0, "0011", 10),
        f("B", 3, "33", 10),
    ]
    r = solve(4, frags, 5)
    assert r.status == "IMPOSSIBLE"
    assert r.ladder.rungs == ()
    assert r.ladder.total_bodies == 0


def test_ladder_28_fragments_many_bodies_takes_distinct_top_n():
    # 14 个二元选择 -> 2^14 份不同正文, 阶梯只取前 N 且名次互不相同。
    frags = []
    for i in range(14):
        frags.append(f(f"lo{i}", i, "00", 1))
        frags.append(f(f"hi{i}", i, "01", 1))
    r = solve(14, frags, 5)
    hexes = [x.hex for x in r.ladder.rungs]
    assert hexes == [
        "00" * 14,
        "00" * 13 + "01",
        "00" * 12 + "0100",
        "00" * 12 + "0101",
        "00" * 11 + "010000",
    ]
    assert len(set(hexes)) == 5
    assert r.ladder.total_bodies == 2 ** 14
    assert r.ladder.exhausted is False
    assert [x.first_diff_position for x in r.ladder.rungs] == [
        None, 13, 12, 13, 11
    ]
    # 每阶见证恰好是该路径选择的 14 条片段。
    for rung in r.ladder.rungs:
        assert rung.fragment_count == 14
        assert rung.total_weight == 14
        assert rung.is_optimal  # 等权 -> 全部正文同为最优
