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
