export interface FragmentInput {
  id: string;
  offset: number;
  payload: string;
  weight: number;
}

export interface ReconstructRequest {
  target_length: number;
  fragments: FragmentInput[];
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
}

export interface ValidationIssue {
  loc: (string | number)[];
  msg: string;
  type: string;
}
