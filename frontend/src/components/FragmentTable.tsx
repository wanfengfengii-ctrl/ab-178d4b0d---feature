export interface DraftRow {
  id: string;
  offset: string;
  payload: string;
  weight: string;
}

interface Props {
  rows: DraftRow[];
  onChange: (rows: DraftRow[]) => void;
  errorMap: Map<string, string>;
}

const FIELDS: { key: keyof DraftRow; title: string; placeholder: string; mono?: boolean }[] = [
  { key: "id", title: "编号", placeholder: "FRG-01" },
  { key: "offset", title: "偏移（零基）", placeholder: "0" },
  { key: "payload", title: "十六进制载荷", placeholder: "DEADBEEF", mono: true },
  { key: "weight", title: "可信权重 1–1000000", placeholder: "100" },
];

export default function FragmentTable({ rows, onChange, errorMap }: Props) {
  const update = (index: number, key: keyof DraftRow, value: string) => {
    const next = rows.map((row, i) => (i === index ? { ...row, [key]: value } : row));
    onChange(next);
  };

  const addRow = () => {
    const n = rows.length + 1;
    onChange([
      ...rows,
      { id: `FRG-${String(n).padStart(2, "0")}`, offset: "0", payload: "", weight: "100" },
    ]);
  };

  const removeRow = (index: number) => {
    onChange(rows.filter((_, i) => i !== index));
  };

  return (
    <div className="table-wrap">
      <table className="frag-table">
        <thead>
          <tr>
            <th className="col-idx">#</th>
            {FIELDS.map((f) => (
              <th key={f.key}>{f.title}</th>
            ))}
            <th className="col-op" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              <td className="col-idx">{i}</td>
              {FIELDS.map((f) => {
                const err = errorMap.get(`${i}.${f.key}`);
                return (
                  <td key={f.key}>
                    <input
                      className={err ? "input-error" : f.mono ? "mono" : ""}
                      value={row[f.key]}
                      placeholder={f.placeholder}
                      spellCheck={false}
                      title={err}
                      onChange={(e) => update(i, f.key, e.target.value)}
                    />
                  </td>
                );
              })}
              <td className="col-op">
                <button
                  type="button"
                  className="btn icon"
                  title="删除该片段"
                  disabled={rows.length <= 2}
                  onClick={() => removeRow(i)}
                >
                  ✕
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        type="button"
        className="btn ghost small"
        onClick={addRow}
        disabled={rows.length >= 28}
      >
        + 添加片段（{rows.length}/28）
      </button>
    </div>
  );
}
