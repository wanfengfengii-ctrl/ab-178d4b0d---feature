import { useEffect, useState } from "react";
import type { CandidateLadder } from "../types";
import { BodyCard } from "./VerdictPanel";

interface Props {
  /** 当前响应携带的阶梯; 未生成/已撤下时为 null */
  ladder: CandidateLadder | null;
  targetLength: number;
  ladderSize: number;
  /** 复核员是否已启用阶梯(决定显示"生成"还是"收起") */
  wanted: boolean;
  /** 阶梯请求在途 */
  busy: boolean;
  onGenerate: () => void;
  onCollapse: () => void;
  onSizeChange: (n: number) => void;
}

const SIZE_OPTIONS = [2, 3, 4, 5];

export default function LadderSection({
  ladder,
  targetLength,
  ladderSize,
  wanted,
  busy,
  onGenerate,
  onCollapse,
  onSizeChange,
}: Props) {
  const [selectedRank, setSelectedRank] = useState(1);

  // 新阶梯到达(或撤下)时回到第一阶, 避免残留选中指向过期正文。
  useEffect(() => {
    setSelectedRank(1);
  }, [ladder]);

  const entries = ladder?.entries ?? [];
  const selected =
    entries.find((e) => e.rank === selectedRank) ?? entries[0] ?? null;

  return (
    <div className="ladder-section">
      <div className="ladder-head">
        <div className="ladder-title">
          <h3>候选阶梯</h3>
          <p className="hint">
            当前高可信证据被否定时, 按得分降序查看最接近的其他正文（每份不同正文只占一阶）。
          </p>
        </div>
        <div className="ladder-controls">
          <label className="ladder-size">
            级数
            <select
              value={ladderSize}
              onChange={(e) => onSizeChange(Number(e.target.value))}
            >
              {SIZE_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          {wanted ? (
            <button
              type="button"
              className="btn ghost"
              onClick={onCollapse}
              disabled={busy}
            >
              收起阶梯
            </button>
          ) : (
            <button
              type="button"
              className="btn ghost"
              onClick={onGenerate}
              disabled={busy}
            >
              {busy ? "阶梯计算中…" : "生成候选阶梯"}
            </button>
          )}
        </div>
      </div>

      {wanted && busy && !ladder && (
        <p className="hint ladder-status">阶梯计算中…</p>
      )}

      {ladder && entries.length === 0 && (
        <p className="hint ladder-status">
          无可列候选（已穷尽）。裁决无法完整还原时不出具候选正文。
        </p>
      )}

      {ladder && entries.length > 0 && (
        <>
          <div className="ladder-body">
            <ol className="rung-list">
              {entries.map((e) => (
                <li key={e.rank}>
                  <button
                    type="button"
                    className={`rung ${selected?.rank === e.rank ? "selected" : ""}`}
                    onClick={() => setSelectedRank(e.rank)}
                  >
                    <span className="rung-rank">#{e.rank}</span>
                    <span className="rung-score mono">
                      权重 {e.total_weight} · {e.fragment_count} 片
                    </span>
                    <span className="rung-diff">
                      {e.diff_from_prev === null
                        ? "当前最优正文"
                        : `与上一阶首异字节: ${e.diff_from_prev}`}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
            {selected && (
              <div className="rung-detail">
                <BodyCard
                  body={selected}
                  length={targetLength}
                  accent={selected.rank === 1}
                  tag={`第 ${selected.rank} 阶 · 权重 ${selected.total_weight} · ${selected.fragment_count} 片`}
                />
              </div>
            )}
          </div>
          <p className="hint ladder-exhaust">
            {ladder.exhausted
              ? entries.length < ladder.requested
                ? `不同正文共 ${entries.length} 份, 不足所请 ${ladder.requested} 阶 —— 已穷尽。`
                : `已列出全部 ${entries.length} 份不同正文 —— 已穷尽。`
              : `仅列出前 ${ladder.requested} 阶, 还有更多不同正文未列出。`}
          </p>
        </>
      )}
    </div>
  );
}
