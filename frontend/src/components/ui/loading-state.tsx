export function LoadingState({ label = "Loading your workspace…" }: {
    label?: string;
}) {
    return <div className="loading-state" role="status" aria-live="polite"><p>{label}</p><div className="loading-state-lines" aria-hidden="true"><span className="skeleton"/><span className="skeleton"/><span className="skeleton"/></div></div>;
}
