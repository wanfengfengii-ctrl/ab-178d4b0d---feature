"""核心重建引擎。

输入: 目标正文长度 L(1..512) 与若干(n<=28)字节片段。
每个片段有唯一编号、零基偏移、非空十六进制载荷与可信权重(1..1_000_000)。

有效方案: 选出的片段两两在重叠处字节完全一致, 且其并集覆盖 [0, L) 的每个字节。
择优: 先最大化总权重; 总权重相同再最大化采用片段数。
裁决:
  - UNIQUE: 所有最优方案还原同一正文;
  - AMBIGUOUS: 最优方案可还原多种正文, 按无符号字节序列序给出最小的两份,
    并附各自的片段见证;
  - IMPOSSIBLE: 不存在完整一致的覆盖(存在缺口, 或片段冲突使覆盖无法完成)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Fragment:
    """一条经过校验的字节片段。payload 为原始字节。"""

    id: str
    offset: int
    payload: bytes
    weight: int

    @property
    def length(self) -> int:
        return len(self.payload)

    @property
    def end(self) -> int:
        return self.offset + len(self.payload)


@dataclass(frozen=True)
class ConflictAlternative:
    position: int
    byte: int
    fragment_ids: tuple[str, ...]


@dataclass(frozen=True)
class WitnessFragment:
    id: str
    offset: int
    payload_hex: str
    weight: int


@dataclass(frozen=True)
class BodyWitness:
    rank: int
    hex: str
    witness_fragment_ids: tuple[str, ...]
    adopted_fragments: tuple[WitnessFragment, ...]


@dataclass(frozen=True)
class ReconstructionResult:
    status: str  # UNIQUE / AMBIGUOUS / IMPOSSIBLE
    target_length: int
    total_weight: Optional[int]
    fragment_count: Optional[int]
    bodies: tuple[BodyWitness, ...]
    conflicts: tuple[ConflictAlternative, ...]
    conflict_positions: tuple[int, ...]
    uncovered_positions: tuple[int, ...]
    impossible_reason: Optional[str]  # GAP / CONFLICT / None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "target_length": self.target_length,
            "optimal": {
                "total_weight": self.total_weight,
                "fragment_count": self.fragment_count,
            },
            "bodies": [
                {
                    "rank": b.rank,
                    "hex": b.hex,
                    "witness_fragment_ids": list(b.witness_fragment_ids),
                    "adopted_fragments": [
                        {
                            "id": f.id,
                            "offset": f.offset,
                            "payload": f.payload_hex,
                            "weight": f.weight,
                        }
                        for f in b.adopted_fragments
                    ],
                }
                for b in self.bodies
            ],
            "conflicts": [
                {
                    "position": c.position,
                    "byte": f"{c.byte:02X}",
                    "fragment_ids": list(c.fragment_ids),
                }
                for c in self.conflicts
            ],
            "conflict_positions": list(self.conflict_positions),
            "uncovered_positions": list(self.uncovered_positions),
            "impossible_reason": self.impossible_reason,
        }


def _build_conflicts(
    length: int, fragments: list[Fragment]
) -> tuple[list[ConflictAlternative], list[int], list[int]]:
    """扫描每个目标字节, 返回冲突候选值、冲突位置与缺口位置。"""

    # position -> byte value -> 覆盖该字节且取该值的片段编号
    by_position: list[dict[int, list[str]]] = [{} for _ in range(length)]
    for frag in fragments:
        for i, byte in enumerate(frag.payload):
            pos = frag.offset + i
            by_position[pos].setdefault(byte, []).append(frag.id)

    conflicts: list[ConflictAlternative] = []
    conflict_positions: list[int] = []
    uncovered: list[int] = []
    for pos, values in enumerate(by_position):
        if not values:
            uncovered.append(pos)
            continue
        if len(values) >= 2:
            conflict_positions.append(pos)
            for byte, ids in sorted(values.items()):
                conflicts.append(
                    ConflictAlternative(pos, byte, tuple(ids))
                )
    return conflicts, conflict_positions, uncovered


def _adjacency(fragments: list[Fragment]) -> list[int]:
    """冲突图: 两片段区间相交且存在不同字节则相邻(不可同时采用)。"""

    n = len(fragments)
    adj = [0] * n
    for i in range(n):
        fi = fragments[i]
        for j in range(i + 1, n):
            fj = fragments[j]
            lo = max(fi.offset, fj.offset)
            hi = min(fi.end, fj.end)
            if lo >= hi:
                continue
            disagree = False
            for pos in range(lo, hi):
                if fi.payload[pos - fi.offset] != fj.payload[pos - fj.offset]:
                    disagree = True
                    break
            if disagree:
                adj[i] |= 1 << j
                adj[j] |= 1 << i
    return adj


def solve(length: int, fragments: list[Fragment]) -> ReconstructionResult:
    """求解重建问题。调用方需已完成全部输入合法性校验。"""

    conflicts, conflict_positions, uncovered = _build_conflicts(length, fragments)
    n = len(fragments)
    full_mask = (1 << length) - 1

    # 若存在任何片段都覆盖不到的位置, 任何选法都不可能完整。
    if uncovered:
        return ReconstructionResult(
            status="IMPOSSIBLE",
            target_length=length,
            total_weight=None,
            fragment_count=None,
 bodies=(),
            conflicts=tuple(conflicts),
            conflict_positions=tuple(conflict_positions),
            uncovered_positions=tuple(uncovered),
            impossible_reason="GAP",
        )

    adj = _adjacency(fragments)
    cover_masks = []
    for frag in fragments:
        m = 0
        for pos in range(frag.offset, frag.end):
            m |= 1 << pos
        cover_masks.append(m)

    # 按偏移自左向右, 权重高者优先, 使包含分支尽早给出高质量可行覆盖。
    order = sorted(range(n), key=lambda k: (fragments[k].offset, -fragments[k].weight, k))
    # order 索引 -> 原始索引的逆映射。
    position_of = [0] * n
    for ordered_index, original_index in enumerate(order):
        position_of[original_index] = ordered_index
    weight = [fragments[k].weight for k in order]
    covers = [cover_masks[k] for k in order]
    # 把邻接位重映到 order 索引空间。
    adj_o = [0] * n
    for a in range(n):
        for b in range(n):
            if adj[order[a]] & (1 << order[b]):
                adj_o[a] |= 1 << b

    best_weight = -1
    best_count = -1
    # body bytes -> 所选片段在 order 空间的位掩码(任一见证即可)
    bodies: dict[bytes, int] = {}

    def record(chosen: int, total: int, count: int) -> None:
        nonlocal best_weight, best_count, bodies
        if (total, count) < (best_weight, best_count):
            return
        buf = bytearray(length)
        bits = chosen
        while bits:
            k = (bits & -bits).bit_length() - 1
            frag = fragments[order[k]]
            for i, byte in enumerate(frag.payload):
                buf[frag.offset + i] = byte
            bits &= bits - 1
        body = bytes(buf)
        if (total, count) > (best_weight, best_count):
            best_weight, best_count = total, count
            bodies = {body: chosen}
        else:
            bodies.setdefault(body, chosen)

    def search(i: int, chosen: int, total: int, count: int, covered: int) -> None:
        # 上界: 当前值 + 所有仍与已选相容的剩余片段(全取)。权重均为正,
        # 若该上界在(总权重, 片段数)序上仍不优于已知最优即可剪枝。
        upper_weight = total
        upper_count = count
        reachable = covered
        for k in range(i, n):
            if not (adj_o[k] & chosen):
                upper_weight += weight[k]
                upper_count += 1
                reachable |= covers[k]
        if reachable != full_mask:
            return  # 剩余相容片段即便全取也补不齐覆盖。
        if (upper_weight, upper_count) < (best_weight, best_count):
            return

        if i == n:
            if covered == full_mask:
                record(chosen, total, count)
            return

        # 包含优先: 与已选无冲突才可取。
        if not (adj_o[i] & chosen):
            search(
                i + 1,
                chosen | (1 << i),
                total + weight[i],
                count + 1,
                covered | covers[i],
            )
        # 排除分支。
        search(i + 1, chosen, total, count, covered)

    search(0, 0, 0, 0, 0)

    if best_weight < 0:
        return ReconstructionResult(
            status="IMPOSSIBLE",
            target_length=length,
            total_weight=None,
            fragment_count=None,
            bodies=(),
            conflicts=tuple(conflicts),
            conflict_positions=tuple(conflict_positions),
            uncovered_positions=(),
            impossible_reason="CONFLICT",
        )

    def make_witness(rank: int, body: bytes, chosen: int) -> BodyWitness:
        ids: list[str] = []
        adopted: list[WitnessFragment] = []
        for original_index, frag in enumerate(fragments):
            if chosen & (1 << position_of[original_index]):
                ids.append(frag.id)
                adopted.append(
                    WitnessFragment(frag.id, frag.offset, frag.payload.hex().upper(), frag.weight)
                )
        return BodyWitness(
            rank=rank,
            hex=body.hex().upper(),
            witness_fragment_ids=tuple(ids),
            adopted_fragments=tuple(adopted),
        )

    # bytes 比较即无符号字节的字典序。
    sorted_bodies = sorted(bodies.items())
    if len(sorted_bodies) == 1:
        body, chosen = sorted_bodies[0]
        result_bodies = (make_witness(1, body, chosen),)
        status = "UNIQUE"
    else:
        result_bodies = tuple(
            make_witness(rank, body, chosen)
            for rank, (body, chosen) in enumerate(sorted_bodies[:2], start=1)
        )
        status = "AMBIGUOUS"

    return ReconstructionResult(
        status=status,
        target_length=length,
        total_weight=best_weight,
        fragment_count=best_count,
        bodies=result_bodies,
        conflicts=tuple(conflicts),
        conflict_positions=tuple(conflict_positions),
        uncovered_positions=(),
        impossible_reason=None,
    )
