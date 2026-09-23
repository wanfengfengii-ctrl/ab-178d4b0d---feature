export interface FragmentInput {
  id: string;
  offset: number;
  payload: string;
  weight: number;
}

export interface ReconstructRequest {
  target_length: number;
  fragments: FragmentInput[];
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

export interface LadderRung {
  rank: number;
  hex: string;
  total_weight: number;
  fragment_count: number;
  witness_fragment_ids: string[];
  adopted_fragments: AdoptedFragment[];
  first_diff_position: number | null;
  is_optimal: boolean;
}

export interface Ladder {
  requested: number;
  total_bodies: number;
  exhausted: boolean;
  rungs: LadderRung[];
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
  ladder?: Ladder;
}

export interface ValidationIssue {
  loc: (string | number)[];
  msg: string;
  type: string;
}
