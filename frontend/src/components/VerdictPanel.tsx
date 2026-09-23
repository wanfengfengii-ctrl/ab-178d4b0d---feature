import type {
  AdoptedFragment,
  BodyWitness,
  ReconstructionResult,
} from "../types";
import { useMemo, useState } from "react";
import HexBodyView from "./HexBodyView";
import ConflictMap from "./ConflictMap";

const STATUS_TEXT: Record<string, { title: string; cls: string; desc: string }> = {
  UNIQUE: {
    title: "UNIQUE · 正文唯一",
    cls: "unique",
    desc: "所有最优方案还原出同一份正文。",
  },
  AMBIGUOUS: {
    title: "AMBIGUOUS · 正文歧义",
    cls: "ambiguous",
    desc: "存在多份互异正文同时达到最优权重；下方按无符号字节序列出最小的两份。",
  },
  IMPOSSIBLE: {
    title: "IMPOSSIBLE · 无法完整还原",
    cls: "impossible",
    desc: "不存在覆盖全部目标字节且互相一致的片段组合。",
  },
};

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

function firstDiff(a: string, b: string): number {
  const n = Math.min(a.length / 2, b.length / 2);
  for (let i = 0; i < n; i++) {
    if (a.slice(i * 2, i * 2 + 2) !== b.slice(i * 2, i * 2 + 2)) return i;
  }
  return n;
}

function BodyCard({
  body,
  length,
  accent,
}: {
  body: BodyWitness;
  length: number;
  accent: boolean;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const coverage = useMemo(
    () => rangesOf(body.adopted_fragments, length),
    [body, length],
  );
  const selectedFrag = body.adopted_fragments.find((f) => f.id === selected) ?? null;

  return (
    <div className={`body-card ${accent ? "accent" : ""}`}>
      <div className="body-card-head">
        <span className="rank">#{body.rank}</span>
        <span className="rank-tag">
          {body.rank === 1 ? "字节序最小正文" : "字节序次小正文"}
        </span>
      </div>
      <HexBodyView
        hex={body.hex}
        length={length}
        coverage={coverage}
        selectedFrag={selectedFrag}
      />
      <div className="witness-head">
        片段见证（{body.witness_fragment_ids.length}）
      </div>
      <ul className="witness-list">
        {body.adopted_fragments.map((f) => (
          <li
            key={f.id}
            className={selected === f.id ? "selected" : ""}
            onMouseEnter={() => setSelected(f.id)}
            onMouseLeave={() => setSelected(null)}
          >
            <span className="w-id">{f.id}</span>
            <span className="w-off">@{f.offset}</span>
            <span className="w-hex mono">{f.payload}</span>
            <span className="w-weight">w={f.weight}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function VerdictPanel({ result }: { result: ReconstructionResult }) {
  const meta = STATUS_TEXT[result.status];
  const hasInputConflicts = result.conflict_positions.length > 0;
  const diffPos =
    result.status === "AMBIGUOUS" && result.bodies.length === 2
      ? firstDiff(result.bodies[0].hex, result.bodies[1].hex)
      : null;

  return (
    <div className="verdict">
      <div className={`verdict-banner ${meta.cls}`}>
        <h2>{meta.title}</h2>
        <p>{meta.desc}</p>
      </div>

      <div className="metrics">
        <div className="metric">
          <span className="m-label">最大总权重</span>
          <span className="m-value">
            {result.optimal.total_weight ?? "—"}
          </span>
        </div>
        <div className="metric">
          <span className="m-label">最优方案片段数</span>
          <span className="m-value">
            {result.optimal.fragment_count ?? "—"}
          </span>
        </div>
        <div className="metric">
          <span className="m-label">目标长度</span>
          <span className="m-value">{result.target_length} B</span>
        </div>
      </div>

      {result.status === "AMBIGUOUS" && diffPos !== null && (
        <div className="notice ambiguous-note">
          两份正文的首个差异位置为字节偏移 <strong>{diffPos}</strong>
          （0 起算）。歧义指“不同最优方案还原出不同正文”，与下方的输入片段冲突不是同一概念。
        </div>
      )}

      {result.status === "IMPOSSIBLE" && (
        <div
          className={`notice ${result.impossible_reason === "GAP" ? "gap-note" : "conflict-note"}`}
        >
          {result.impossible_reason === "GAP"
            ? "原因：存在缺口——部分目标字节没有任何片段能覆盖。"
            : "原因：冲突——每个字节虽都有片段覆盖, 但无法选出一组互不矛盾的片段完成全覆盖。"}
        </div>
      )}

      {result.bodies.length > 0 && (
        <div className="bodies">
          {result.bodies.map((b, i) => (
            <BodyCard
              key={b.rank}
              body={b}
              length={result.target_length}
              accent={i === 0}
            />
          ))}
        </div>
      )}

      {/* 输入层面的片段冲突/缺口图: 任何裁决下都展示, 便于区分冲突与歧义 */}
      <ConflictMap
        length={result.target_length}
        conflictPositions={result.conflict_positions}
        uncoveredPositions={result.uncovered_positions}
        conflicts={result.conflicts}
        showAlternatives={result.status === "IMPOSSIBLE"}
      />
      {hasInputConflicts && result.status !== "IMPOSSIBLE" && (
        <p className="hint conflict-hint">
          琥珀色为输入片段之间互相矛盾的位置；最优方案{result.status === "AMBIGUOUS" ? "在不同正文中分别" : "已"}绕开它们。
          “片段冲突”描述输入证据, “正文歧义”描述裁决结果, 两者独立。
        </p>
      )}
    </div>
  );
}
