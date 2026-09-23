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

def test_ladder_absent_unless_requested():
    # 未启用阶梯时结果与原契约完全一致: 无 ladder 字段。
    frags = [
        f("A", 0, "AABBCCDD", 10),
        f("B", 3, "DDEEFF", 10),
    ]
    r = solve(6, frags)
    assert r.ladder is None
    assert "ladder" not in r.to_dict()


def test_ladder_ranks_bodies_by_score_desc():
    # 三份正文得分 101/100/99, 阶梯须严格按得分降序。
    frags = [
        f("X", 0, "00", 100),
        f("Y", 0, "01", 99),
        f("W", 0, "02", 98),
        f("Z", 1, "FF", 1),
    ]
    r = solve(2, frags, ladder_size=3)
    assert r.status == "UNIQUE"
    lad = r.ladder
    assert lad is not None and lad.requested == 3
    assert lad.exhausted is True
    assert [(e.hex, e.total_weight, e.fragment_count) for e in lad.entries] == [
        ("00FF", 101, 2),
        ("01FF", 100, 2),
        ("02FF", 99, 2),
    ]
    # 与上一阶首次不同的字节位置; 第一阶为 None。
    assert [e.diff_from_prev for e in lad.entries] == [None, 0, 0]
    # 阶梯第一阶与裁决正文一致。
    assert lad.entries[0].hex == r.bodies[0].hex
    assert (lad.entries[0].total_weight, lad.entries[0].fragment_count) == (
        r.total_weight,
        r.fragment_count,
    )


def test_ladder_score_tie_broken_by_unsigned_body_order():
    # 四份同分正文, 取前 3 阶须按无符号字节升序(0x7F < 0x80)。
    frags = [
        f("A", 0, "02", 10),
        f("B", 0, "01", 10),
        f("C", 0, "7F", 10),
        f("D", 0, "80", 10),
    ]
    r = solve(1, frags, ladder_size=3)
    assert r.status == "AMBIGUOUS"
    lad = r.ladder
    assert [e.hex for e in lad.entries] == ["01", "02", "7F"]
    assert all((e.total_weight, e.fragment_count) == (10, 1) for e in lad.entries)
    # 还有第 4 份正文 80 未列出 -> 未穷尽。
    assert lad.exhausted is False


def test_ladder_dedupes_multiple_coverings_of_same_body():
    # 正文 0000 有多份重复覆盖(冗余一致片段), 阶梯中只占一阶,
    # 且见证为该正文可达的最优(全相容片段)。
    frags = [
        f("MAIN", 0, "0000", 10),
        f("DUP1", 0, "00", 5),
        f("DUP2", 1, "00", 5),
        f("ALT", 0, "0101", 9),
    ]
    r = solve(2, frags, ladder_size=2)
    lad = r.ladder
    assert lad.exhausted is True
    assert len(lad.entries) == 2
    top = lad.entries[0]
    assert top.hex == "0000"
    assert (top.total_weight, top.fragment_count) == (20, 3)
    # 见证按片段编号升序。
    assert top.witness_fragment_ids == ("DUP1", "DUP2", "MAIN")
    assert lad.entries[1].hex == "0101"
    assert (lad.entries[1].total_weight, lad.entries[1].fragment_count) == (9, 1)
    assert lad.entries[1].diff_from_prev == 0


def test_ladder_witness_ids_sorted_ascending():
    # 输入顺序与编号序不同, 阶梯见证仍按编号升序。
    frags = [
        f("ZZ", 0, "AA", 10),
        f("AA", 1, "BB", 10),
    ]
    r = solve(2, frags, ladder_size=2)
    lad = r.ladder
    assert len(lad.entries) == 1
    assert lad.entries[0].witness_fragment_ids == ("AA", "ZZ")
    assert [a.id for a in lad.entries[0].adopted_fragments] == ["AA", "ZZ"]


def test_ladder_exhausted_when_fewer_bodies_than_requested():
    frags = [
        f("A", 0, "AABB", 10),
        f("B", 1, "BB", 3),
    ]
    r = solve(2, frags, ladder_size=5)
    lad = r.ladder
    assert lad.requested == 5
    assert len(lad.entries) == 1
    assert lad.exhausted is True


def test_ladder_first_rungs_match_verdict_bodies_when_ambiguous():
    frags = [
        f("X", 0, "00", 100),
        f("Y", 0, "01", 100),
        f("Z", 1, "FF", 1),
    ]
    r = solve(2, frags, ladder_size=2)
    assert r.status == "AMBIGUOUS"
    lad = r.ladder
    assert [e.hex for e in lad.entries] == [b.hex for b in r.bodies]
    assert lad.entries[1].diff_from_prev == 0


def test_ladder_never_fabricates_candidates_when_impossible():
    # GAP 与 CONFLICT 两种不可行情形下阶梯都必须为空且已穷尽。
    gap = solve(4, [f("A", 0, "0011", 10), f("B", 3, "33", 10)], ladder_size=4)
    conflict = solve(3, [f("A", 0, "0000", 10), f("B", 1, "0101", 10)], ladder_size=4)
    for r, reason in [(gap, "GAP"), (conflict, "CONFLICT")]:
        assert r.status == "IMPOSSIBLE"
        assert r.impossible_reason == reason
        assert r.ladder is not None
        assert r.ladder.entries == ()
        assert r.ladder.exhausted is True
        assert r.ladder.requested == 4


def test_ladder_28_fragments_many_distinct_bodies():
    # 28 片 = 14 个位置 x 2 个等权候选 -> 16384 份不同正文同分,
    # 前 5 阶须按无符号字节序, 且毫秒级完成。
    frags = []
    for i in range(14):
        frags.append(f(f"lo{i}", i, "00", 1))
        frags.append(f(f"hi{i}", i, "01", 1))
    r = solve(14, frags, ladder_size=5)
    lad = r.ladder
    assert [e.hex for e in lad.entries] == [
        "00" * 14,
        "00" * 13 + "01",
        "00" * 12 + "01" + "00",
        "00" * 12 + "01" + "01",
        "00" * 11 + "01" + "00" * 2,
    ]
    assert [e.diff_from_prev for e in lad.entries] == [None, 13, 12, 13, 11]
    assert lad.exhausted is False
    assert all((e.total_weight, e.fragment_count) == (14, 14) for e in lad.entries)


def test_ladder_28_fragments_duplicate_coverings_do_not_steal_rungs():
    # 28 片: 1 个互斥备选 + 27 个与正文 0000 一致的冗余片段。
    # 同一正文的海量重复覆盖不得重复占位, 不同正文各居一阶。
    frags = [f("ALT", 0, "FFFF", 10)]
    for i in range(27):
        frags.append(f(f"R{i:02d}", 0, "0000", 1))
    r = solve(2, frags, ladder_size=5)
    assert r.status == "UNIQUE"
    lad = r.ladder
    assert lad.exhausted is True
    assert [e.hex for e in lad.entries] == ["0000", "FFFF"]
    top = lad.entries[0]
    assert (top.total_weight, top.fragment_count) == (27, 27)
    assert len(top.witness_fragment_ids) == 27
    assert lad.entries[1].diff_from_prev == 0
