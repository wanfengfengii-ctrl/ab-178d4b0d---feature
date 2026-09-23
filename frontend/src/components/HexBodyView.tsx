import type { AdoptedFragment } from "../types";

interface Props {
  hex: string;
  length: number;
  coverage: string[][]; // 每个字节由哪些见证片段覆盖
  selectedFrag: AdoptedFragment | null;
}

const BYTES_PER_ROW = 16;

function asciiRepr(byte: string): string {
  const n = parseInt(byte, 16);
  return n >= 0x20 && n <= 0x7e ? String.fromCharCode(n) : "·";
}

export default function HexBodyView({ hex, length, coverage, selectedFrag }: Props) {
  const bytes: string[] = [];
  for (let i = 0; i < length; i++) {
    bytes.push(hex.slice(i * 2, i * 2 + 2) || "??");
  }
  const rows = Math.ceil(length / BYTES_PER_ROW);
  const selectedRange = selectedFrag
    ? {
        start: selectedFrag.offset,
        end: selectedFrag.offset + selectedFrag.payload.length / 2,
        id: selectedFrag.id,
      }
    : null;

  return (
    <div className="hex-view">
      <table>
        <thead>
          <tr>
            <th className="addr-col">偏移</th>
            {Array.from({ length: BYTES_PER_ROW }, (_, i) => (
              <th key={i}>{i.toString(16).toUpperCase().padStart(2, "0")}</th>
            ))}
            <th className="ascii-col">ASCII</th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }, (_, r) => {
            const base = r * BYTES_PER_ROW;
            const rowBytes = bytes.slice(base, base + BYTES_PER_ROW);
            return (
              <tr key={r}>
                <td className="addr-col">
                  {base.toString(16).toUpperCase().padStart(4, "0")}
                </td>
                {rowBytes.map((b, j) => {
                  const pos = base + j;
                  const ids = coverage[pos] ?? [];
                  let cls = "hex-cell";
                  if (selectedRange && pos >= selectedRange.start && pos < selectedRange.end) {
                    cls += " highlight";
                  } else if (ids.length >= 2) {
                    cls += " overlap";
                  }
                  const title = ids.length
                    ? `偏移 ${pos} · 0x${b} · 见证: ${ids.join(", ")}`
                    : `偏移 ${pos} · 0x${b}`;
                  return (
                    <td key={j} className={cls} title={title}>
                      {b}
                    </td>
                  );
                })}
                {rowBytes.length < BYTES_PER_ROW &&
                  Array.from({ length: BYTES_PER_ROW - rowBytes.length }, (_, j) => (
                    <td key={`pad-${j}`} className="hex-cell pad" />
                  ))}
                <td className="ascii-col mono">
                  {rowBytes.map(asciiRepr).join("")}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
