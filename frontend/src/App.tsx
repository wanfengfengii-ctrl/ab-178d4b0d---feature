import { useCallback, useMemo, useRef, useState } from "react";
import type {
  FragmentInput,
  ReconstructionResult,
  ValidationIssue,
} from "./types";
import { ApiError, reconstruct } from "./api";
import { SAMPLES } from "./sampleData";
import FragmentTable, { type DraftRow } from "./components/FragmentTable";
import ImportPanel from "./components/ImportPanel";
import VerdictPanel from "./components/VerdictPanel";
import ValidationErrors from "./components/ValidationErrors";

interface ClientIssue {
  row?: number;
  field?: "id" | "offset" | "payload" | "weight";
  msg: string;
}

const FIELD_LABELS: Record<string, string> = {
  id: "编号",
  offset: "偏移",
  payload: "载荷",
  weight: "权重",
};

export default function App() {
  const [targetLength, setTargetLength] = useState("8");
  const [rows, setRows] = useState<DraftRow[]>(() => {
    const starter = SAMPLES[0].request;
    return starter.fragments.map((f) => ({
      id: f.id,
      offset: String(f.offset),
      payload: f.payload,
      weight: String(f.weight),
    }));
  });
  const [result, setResult] = useState<ReconstructionResult | null>(null);
  const [issues, setIssues] = useState<ClientIssue[]>([]);
  const [loading, setLoading] = useState(false);
  const [stale, setStale] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);

  const clientCheck = useCallback(
    (length: number, drafts: DraftRow[]): ClientIssue[] => {
      const found: ClientIssue[] = [];
      const seen = new Map<string, number>();
      drafts.forEach((row, i) => {
        if (!row.id.trim()) {
          found.push({ row: i, field: "id", msg: "编号不能为空" });
        } else if (seen.has(row.id)) {
          found.push({
            row: i,
            field: "id",
            msg: `编号与第 ${(seen.get(row.id) ?? 0) + 1} 行重复`,
          });
        } else {
          seen.set(row.id, i);
        }
        const offset = row.offset.trim();
        if (!/^-?\d+$/.test(offset)) {
          found.push({ row: i, field: "offset", msg: "偏移必须是整数" });
        } else if (Number(offset) < 0) {
          found.push({ row: i, field: "offset", msg: "偏移不能为负" });
        }
        const hex = row.payload.replace(/\s+/g, "");
        if (!hex) {
          found.push({ row: i, field: "payload", msg: "载荷不能为空" });
        } else if (hex.length % 2 !== 0 || !/^[0-9a-fA-F]+$/.test(hex)) {
          found.push({ row: i, field: "payload", msg: "十六进制格式错误" });
        } else {
          const end = Number(offset) + hex.length / 2;
          if (/^\d+$/.test(offset) && end > length) {
            found.push({
              row: i,
              field: "offset",
              msg: `越界: 末字节位于 ${end - 1}, 目标长度为 ${length}`,
            });
          }
        }
        const weight = row.weight.trim();
        if (!/^\d+$/.test(weight)) {
          found.push({ row: i, field: "weight", msg: "权重必须是正整数" });
        } else {
          const w = Number(weight);
          if (w < 1 || w > 1_000_000) {
            found.push({ row: i, field: "weight", msg: "权重须在 1 至 1000000 之间" });
          }
        }
      });
      return found;
    },
    [],
  );

  const invalidate = useCallback(() => {
    // 修改输入后立即撤下旧裁决, 并作废任何在途请求, 防止旧响应晚到覆盖状态。
    seqRef.current += 1;
    abortRef.current?.abort();
    setStale(true);
    setIssues([]);
  }, []);

  const handleSubmit = useCallback(async () => {
    const length = Number(targetLength);
    const local: ClientIssue[] = [];
    if (!/^\d+$/.test(targetLength.trim()) || length < 1 || length > 512) {
      local.push({ msg: "目标长度必须是 1 至 512 的整数" });
    }
    if (rows.length < 2 || rows.length > 28) {
      local.push({ msg: `片段数量必须在 2 至 28 之间(当前 ${rows.length})` });
    }
    if (targetLength.trim() !== "" && rows.length >= 2 && rows.length <= 28) {
      local.push(...clientCheck(Number(targetLength) || 0, rows));
    }
    if (local.length > 0) {
      setIssues(local);
      setResult(null);
      setStale(false);
      return;
    }

    const fragments: FragmentInput[] = rows.map((row) => ({
      id: row.id,
      offset: Number(row.offset.trim()),
      payload: row.payload.replace(/\s+/g, "").toUpperCase(),
      weight: Number(row.weight.trim()),
    }));

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const seq = ++seqRef.current;
    setLoading(true);
    setIssues([]);
    try {
      const res = await reconstruct(
        { target_length: length, fragments },
        controller.signal,
      );
      if (seq === seqRef.current) {
        setResult(res);
        setStale(false);
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      if (seq !== seqRef.current) return;
      if (err instanceof ApiError && err.status === 422) {
        setIssues(err.issues.map(toClientIssue));
        setResult(null);
      } else {
        setIssues([
          { msg: err instanceof Error ? err.message : "网络或服务错误" },
        ]);
      }
      setStale(false);
    } finally {
      if (seq === seqRef.current) setLoading(false);
    }
  }, [targetLength, rows, clientCheck]);

  const loadRequest = useCallback(
    (length: number, fragments: FragmentInput[]) => {
      setTargetLength(String(length));
      setRows(
        fragments.map((f) => ({
          id: f.id,
          offset: String(f.offset),
          payload: f.payload,
          weight: String(f.weight),
        })),
      );
      setResult(null);
      setIssues([]);
      setStale(true);
    },
    [],
  );

  const errorFieldMap = useMemo(() => {
    const map = new Map<string, string>();
    issues.forEach((iss) => {
      if (iss.row !== undefined && iss.field) {
        map.set(`${iss.row}.${iss.field}`, iss.msg);
      }
    });
    return map;
  }, [issues]);

  return (
    <div className="app">
      <header className="topbar">
        <h1>档案片段重建台</h1>
        <span className="subtitle">
          重叠字节片段 · 权重择优 · 冲突与歧义复核
        </span>
      </header>

      <main className="layout">
        <section className="panel input-panel">
          <div className="panel-head">
            <h2>输入</h2>
            <div className="head-actions">
              <button
                type="button"
                className="btn ghost"
                onClick={() => setImportOpen(true)}
              >
                导入 JSON
              </button>
            </div>
          </div>

          <div className="samples">
            {SAMPLES.map((s) => (
              <button
                key={s.key}
                type="button"
                className="chip"
                title={s.description}
                onClick={() =>
                  loadRequest(s.request.target_length, s.request.fragments)
                }
              >
                {s.label}
              </button>
            ))}
          </div>

          <label className="length-row">
            目标正文长度（字节，1–512）
            <input
              type="number"
              min={1}
              max={512}
              value={targetLength}
              onChange={(e) => {
                setTargetLength(e.target.value);
                invalidate();
              }}
            />
          </label>

          <FragmentTable
            rows={rows}
            onChange={(next) => {
              setRows(next);
              invalidate();
            }}
            errorMap={errorFieldMap}
          />

          <div className="submit-row">
            <button
              type="button"
              className="btn primary"
              onClick={handleSubmit}
              disabled={loading}
            >
              {loading ? "裁决中…" : "提交重建"}
            </button>
            {stale && (
              <span className="stale-note">
                输入已修改 — 旧裁决已撤下, 请重新提交
              </span>
            )}
          </div>

          {issues.length > 0 && <ValidationErrors issues={issues} />}
        </section>

        <section className="panel result-panel">
          {result && !stale ? (
            <VerdictPanel result={result} />
          ) : (
            <div className="empty-state">
              <p>
                {stale
                  ? "裁决已撤下。提交修改后的输入以获得新裁决。"
                  : "提交片段后, 这里展示正文十六进制、采用片段与冲突位置。"}
              </p>
              <ul className="legend">
                <li><span className="swatch gap" /> 缺口（无片段覆盖）</li>
                <li><span className="swatch conflict" /> 片段冲突位置</li>
                <li><span className="swatch highlight" /> 见证片段覆盖区</li>
              </ul>
            </div>
          )}
        </section>
      </main>

      {importOpen && (
        <ImportPanel
          onClose={() => setImportOpen(false)}
          onImport={(length, fragments) => {
            loadRequest(length, fragments);
            setImportOpen(false);
          }}
        />
      )}

      <footer className="foot">
        字段定位错误均返回 HTTP 422 · 择优规则：先总权重，后片段数
      </footer>
    </div>
  );
}

function toClientIssue(iss: ValidationIssue): ClientIssue {
  // loc 形如 ["body","fragments",2,"payload"] 或 ["body","target_length"]
  const loc = iss.loc;
  const out: ClientIssue = { msg: iss.msg };
  const fragIdx = loc.indexOf("fragments");
  if (fragIdx >= 0 && typeof loc[fragIdx + 1] === "number") {
    out.row = loc[fragIdx + 1] as number;
    const field = loc[fragIdx + 2];
    if (field === "id" || field === "offset" || field === "payload" || field === "weight") {
      out.field = field;
      out.msg = `${FIELD_LABELS[field]}: ${iss.msg}`;
    }
  } else if (loc.includes("target_length")) {
    out.msg = `目标长度: ${iss.msg}`;
  } else if (loc.includes("fragments")) {
    out.msg = `片段列表: ${iss.msg}`;
  }
  return out;
}
