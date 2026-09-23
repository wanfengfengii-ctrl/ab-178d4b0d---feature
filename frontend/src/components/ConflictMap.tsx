import type { ConflictAlternative } from "../types";
import { useMemo, useState } from "react";

interface Props {
  length: number;
  conflictPositions: number[];
  uncoveredPositions: number[];
  conflicts: ConflictAlternative[];
  showAlternatives: boolean;
}

const CELLS_PER_ROW = 32;

export default function ConflictMap({
  length,
  conflictPositions,
  uncoveredPositions,
  conflicts,
  showAlternatives,
}: Props) {
  const [active, setActive] = useState<number | null>(null);
  const conflictSet = useMemo(() => new Set(conflictPositions), [conflictPositions]);
  const gapSet = useMemo(() => new Set(uncoveredPositions), [uncoveredPositions]);

  const rows = Math.max(1, Math.ceil(length / CELLS_PER_ROW));
  const activeAlts = conflicts.filter((c) => c.position === active);

  if (conflictPositions.length === 0 && uncoveredPositions.length === 0) {
    return (
      <div className="conflict-map clean">
        <h4>冲突与缺口扫描</h4>
        <p className="hint">全部 {length} 个目标字节在输入片段中均有且仅有一致取值。</p>
      </div>
    );
  }

  return (
    <div className="conflict-map">
      <h4>冲突与缺口扫描</h4>
      <div className="raster">
        {Array.from({ length: rows }, (_, r) => {
          const base = r * CELLS_PER_ROW;
          return (
            <div key={r} className="raster-row">
              <span className="raster-addr">
                {base.toString(16).toUpperCase().padStart(4, "0")}
              </span>
              {Array.from({ length: CELLS_PER_ROW }, (_, j) => {
                const pos = base + j;
                if (pos >= length) return <span key={j} className="cell oob" />;
                const isGap = gapSet.has(pos);
                const isConflict = conflictSet.has(pos);
                const cls = `cell${isGap ? " gap" : ""}${isConflict ? " conflict" : ""}${
                  active === pos ? " active" : ""
                }`;
                return (
                  <span
                    key={j}
                    className={cls}
                    title={
                      isGap
                        ? `偏移 ${pos}: 缺口（无片段覆盖）`
                        : `偏移 ${pos}: 片段冲突（点击查看各方取值）`
                    }
                    onClick={isConflict ? () => setActive(active === pos ? null : pos) : undefined}
                  />
                );
              })}
            </div>
          );
        })}
      </div>
      <div className="raster-legend">
        <span><i className="cell conflict mini" /> 片段冲突</span>
        <span><i className="cell gap mini" /> 缺口</span>
        <span className="hint">点击冲突格查看各片段主张的字节</span>
      </div>

      {showAlternatives && activeAlts.length > 0 && (
        <div className="alt-box">
          <strong>偏移 {active} 的冲突各方：</strong>
          <ul>
            {activeAlts.map((alt, i) => (
              <li key={i}>
                <code>0x{alt.byte}</code> ← 片段 {alt.fragment_ids.join(", ")}
              </li>
            ))}
          </ul>
        </div>
      )}
      {!showAlternatives && activeAlts.length > 0 && (
        <div className="alt-box">
          <strong>偏移 {active} 的冲突各方（仅作证据展示, 最优方案已取舍）：</strong>
          <ul>
            {activeAlts.map((alt, i) => (
              <li key={i}>
                <code>0x{alt.byte}</code> ← 片段 {alt.fragment_ids.join(", ")}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
