import type { ReconstructRequest } from "./types";

export interface Sample {
  key: string;
  label: string;
  description: string;
  request: ReconstructRequest;
}

export const SAMPLES: Sample[] = [
  {
    key: "even-split",
    label: "等分正文",
    description: "两片片段在交界处重叠且字节一致 → UNIQUE。",
    request: {
      target_length: 8,
      fragments: [
        { id: "FRG-01", offset: 0, payload: "DEADBEEFCAFE", weight: 100 },
        { id: "FRG-02", offset: 4, payload: "CAFEBABE", weight: 80 },
      ],
    },
  },
  {
    key: "mutex-high-weight",
    label: "高权互斥",
    description: "高权片段与另一路在首字节互斥, 算法须权衡总权重。",
    request: {
      target_length: 4,
      fragments: [
        { id: "HI", offset: 0, payload: "01020304", weight: 500 },
        { id: "LO-A", offset: 0, payload: "FF", weight: 300 },
        { id: "LO-B", offset: 1, payload: "0203", weight: 300 },
        { id: "TAIL", offset: 3, payload: "04", weight: 1 },
      ],
    },
  },
  {
    key: "ambiguous",
    label: "正文歧义",
    description: "首字节两个互斥选项等权, 后续字节共用同一片段 → 两种最优正文, AMBIGUOUS。",
    request: {
      target_length: 4,
      fragments: [
        { id: "OPT-A", offset: 0, payload: "41", weight: 100 },
        { id: "OPT-B", offset: 0, payload: "42", weight: 100 },
        { id: "TAIL", offset: 1, payload: "414141", weight: 10 },
      ],
    },
  },
  {
    key: "gap",
    label: "缺口",
    description: "中间两个字节没有任何片段覆盖 → IMPOSSIBLE / GAP。",
    request: {
      target_length: 6,
      fragments: [
        { id: "HEAD", offset: 0, payload: "1122", weight: 50 },
        { id: "TAIL", offset: 4, payload: "5566", weight: 50 },
      ],
    },
  },
  {
    key: "conflict",
    label: "冲突致不可行",
    description: "无缺口, 但唯一能覆盖中间字节的两片互相矛盾 → IMPOSSIBLE / CONFLICT。",
    request: {
      target_length: 3,
      fragments: [
        { id: "X", offset: 0, payload: "0000", weight: 10 },
        { id: "Y", offset: 1, payload: "0101", weight: 10 },
      ],
    },
  },
];
