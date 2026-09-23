export interface FragmentInput {
  id: string;
  offset: number;
  payload: string;
  weight: number;
}

export interface ReconstructRequest {
  target_length: number;
  fragments: FragmentInput[];
  /** 可选: 候选阶梯级数(2–5); 不提供时响应保持原契约 */
  ladder_size?: number;
}

export interface AdoptedFragment {
  id: string;
  offset: number;
  payload: string;
  weight: number;
}

export interface BodyWitness {
  rank: number;
  hex: string;
  witness_fragment_ids: string[];
  adopted_fragments: AdoptedFragment[];
}

export interface LadderEntry {
  rank: number;
  hex: string;
  total_weight: number;
  fragment_count: number;
  /** 与上一阶正文首次不同的字节位置(零起算); 第一阶为 null */
  diff_from_prev: number | null;
  witness_fragment_ids: string[];
  adopted_fragments: AdoptedFragment[];
}

export interface CandidateLadder {
  requested: number;
  /** true 表示已列出全部现存不同正文(不足请求级数时必然已穷尽) */
  exhausted: boolean;
  entries: LadderEntry[];
}

export interface ConflictAlternative {
  position: number;
  byte: string;
  fragment_ids: string[];
}

export type Verdict = "UNIQUE" | "AMBIGUOUS" | "IMPOSSIBLE";
export type ImpossibleReason = "GAP" | "CONFLICT" | null;

export interface ReconstructionResult {
  status: Verdict;
  target_length: number;
  optimal: {
    total_weight: number | null;
    fragment_count: number | null;
  };
  bodies: BodyWitness[];
  conflicts: ConflictAlternative[];
  conflict_positions: number[];
  uncovered_positions: number[];
  impossible_reason: ImpossibleReason;
  /** 仅在请求携带 ladder_size 时存在 */
  ladder?: CandidateLadder;
}

export interface ValidationIssue {
  loc: (string | number)[];
  msg: string;
  type: string;
}
