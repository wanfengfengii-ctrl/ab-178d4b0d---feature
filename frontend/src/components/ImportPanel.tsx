import { useState } from "react";
import type { FragmentInput, ReconstructRequest } from "../types";

interface Props {
  onClose: () => void;
  onImport: (targetLength: number, fragments: FragmentInput[]) => void;
}

const TEMPLATE = JSON.stringify(
  {
    target_length: 4,
    fragments: [
      { id: "FRG-01", offset: 0, payload: "AABB", weight: 100 },
      { id: "FRG-02", offset: 2, payload: "BBCC", weight: 80 },
    ],
  } satisfies ReconstructRequest,
  null,
  2,
);

export default function ImportPanel({ onClose, onImport }: Props) {
  const [text, setText] = useState(TEMPLATE);
  const [error, setError] = useState<string | null>(null);

  const doImport = () => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch (e) {
      setError(`JSON 解析失败: ${e instanceof Error ? e.message : String(e)}`);
      return;
    }
    const obj = parsed as Partial<ReconstructRequest> | null;
    if (typeof obj !== "object" || obj === null) {
      setError("顶层必须是对象");
      return;
    }
    if (
      typeof obj.target_length !== "number" ||
      !Array.isArray(obj.fragments)
    ) {
      setError("必须包含数值型 target_length 与数组 fragments");
      return;
    }
    setError(null);
    onImport(
      obj.target_length,
      obj.fragments.map((f) => ({
        id: String(f.id),
        offset: Number(f.offset),
        payload: String(f.payload),
        weight: Number(f.weight),
      })),
    );
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>导入片段 JSON</h3>
        <p className="hint">
          粘贴完整请求对象；非法内容将由业务 API 返回 422 并逐字段标注。
        </p>
        <textarea
          className="import-area mono"
          value={text}
          spellCheck={false}
          onChange={(e) => setText(e.target.value)}
          rows={16}
        />
        {error && <div className="error-banner">{error}</div>}
        <div className="modal-actions">
          <button type="button" className="btn ghost" onClick={onClose}>
            取消
          </button>
          <button type="button" className="btn primary" onClick={doImport}>
            导入到编辑表
          </button>
        </div>
      </div>
    </div>
  );
}
