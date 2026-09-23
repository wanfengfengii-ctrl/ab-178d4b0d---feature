import { useMemo, useState } from "react";
import type { AdoptedFragment, Ladder, LadderRung } from "../types";
import HexBodyView from "./HexBodyView";

function rangesOf(
  fragments: AdoptedFragment[],
  length: number,
): string[][] {
  const cover: string[][] = Array.from({ length }, () => []);
  for (const frag of fragments) {
    const n = frag.payload.length / 2;
    for (let p = frag.offset; p < frag.offset + n; p++) {
      cover[p]?.push(frag.id);
    }
  }
  return cover;
}

function RungDetail({ rung, length }: { rung: LadderRung; length: number }) {
  const [selected, setSelected] = useState<string | null>(null);
  const coverage = useMemo(
    () => rangesOf(rung.adopted_fragments, length),
    [rung, length],
  );
  const selectedFrag =
    rung.adopted_fragments.find((frag) => frag.id === selected) ?? null;

  return (
    <div className="ladder-detail">
      <HexBodyView
        hex={rung.hex}
        length={length}
        coverage={coverage}
        selectedFrag={selectedFrag}
        markPosition={rung.first_diff_position}
      />
      <div className="witness-head">
        片段见证（{rung.witness_fragment_ids.length}）· 该正文可达到的最大总权重{" "}
        {rung.total_weight}
      </div>
      <ul className="witness-list">
        {rung.adopted_fragments.map((frag) => (
          <li
            key={frag.id}
            className={selected === frag.id ? "selected" : ""}
            onMouseEnter={() => setSelected(frag.id)}
            onMouseLeave={() => setSelected(null)}
          >
            <span className="w-id">{frag.id}</span>
            <span className="w-off">@{frag.offset}</span>
            <span className="w-hex mono">{frag.payload}</span>
            <span className="w-weight">w={frag.weight}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function LadderPanel({
  ladder,
  length,
}: {
  ladder: Ladder;
  length: number;
}) {
  const [activeRank, setActiveRank] = useState(1);
  const rungs = ladder.rungs;

  if (rungs.length === 0) {
    return (
      <div className="ladder">
        <h4>候选阶梯（{ladder.requested} 级）</h4>
        <p className="hint ladder-empty">
          不存在任何完整一致覆盖 —— IMPOSSIBLE 时不伪造候选正文。
        </p>
      </div>
    );
  }

  const active =
    rungs.find((r) => r.rank === activeRank) ?? rungs[0];

  return (
    <div className="ladder">
      <div className="ladder-head">
        <h4>候选阶梯 · 高可信证据被否定时最接近的其他正文</h4>
        <span className="ladder-meta">
          共 {ladder.total_bodies} 份不同正文 · 按可达最大总权重与片段数计分,
          同分按无符号字节序
          {ladder.exhausted ? " · 已穷尽全部正文" : ` · 仅展示前 ${rungs.length} 份`}
        </span>
      </div>

      <div className="ladder-tabs" role="tablist">
        {rungs.map((r) => (
          <button
            key={r.rank}
            type="button"
            role="tab"
            aria-selected={r.rank === active.rank}
            className={`ladder-tab${r.rank === active.rank ? " active" : ""}${
              r.is_optimal ? " optimal" : ""
            }`}
            onClick={() => setActiveRank(r.rank)}
            title={
              r.is_optimal
                ? "与裁决正文同为最优得分"
                : "得分低于裁决最优"
            }
          >
            <span className="lt-rank">第 {r.rank} 阶</span>
            <span className="lt-score mono">
              Σw={r.total_weight} · {r.fragment_count} 片
            </span>
            <span className="lt-hex mono">
              {r.hex.length > 16 ? `${r.hex.slice(0, 16)}…` : r.hex}
            </span>
          </button>
        ))}
      </div>

      <div className="ladder-body">
        <div className="ladder-body-head">
          <span className={`rank-badge${active.is_optimal ? " optimal" : ""}`}>
            {active.is_optimal ? "最优正文" : "次优正文"}
          </span>
          {active.first_diff_position !== null && (
            <span className="diff-badge">
              与上一阶首次不同：字节偏移 {active.first_diff_position}（0 起算）
            </span>
          )}
        </div>
        <RungDetail key={active.rank} rung={active} length={length} />
      </div>
    </div>
  );
}
