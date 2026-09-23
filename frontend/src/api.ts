import type {
  ReconstructionResult,
  ReconstructRequest,
  ValidationIssue,
} from "./types";

export class ApiError extends Error {
  readonly issues: ValidationIssue[];
  readonly status: number;

  constructor(status: number, issues: ValidationIssue[]) {
    super(`请求失败: HTTP ${status}`);
    this.status = status;
    this.issues = issues;
  }
}

export async function reconstruct(
  request: ReconstructRequest,
  signal?: AbortSignal,
): Promise<ReconstructionResult> {
  const resp = await fetch("/api/reconstruct", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });

  if (resp.status === 422) {
    const data = await resp.json();
    throw new ApiError(422, data.detail ?? []);
  }
  if (!resp.ok) {
    throw new ApiError(resp.status, [
      { loc: ["body"], msg: `服务异常: HTTP ${resp.status}`, type: "http_error" },
    ]);
  }
  return (await resp.json()) as ReconstructionResult;
}
