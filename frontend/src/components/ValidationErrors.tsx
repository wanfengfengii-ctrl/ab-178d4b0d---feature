interface Issue {
  row?: number;
  field?: string;
  msg: string;
}

export default function ValidationErrors({ issues }: { issues: Issue[] }) {
  return (
    <div className="error-panel">
      <h4>输入被拒绝（HTTP 422）— 共 {issues.length} 处</h4>
      <ul>
        {issues.map((iss, i) => (
          <li key={i}>
            {iss.row !== undefined && (
              <span className="loc-tag">
                fragments[{iss.row}]
                {iss.field ? `.${iss.field}` : ""}
              </span>
            )}
            {iss.msg}
          </li>
        ))}
      </ul>
    </div>
  );
}
