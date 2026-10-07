"use client";
export default function ErrorPage({ reset }: { reset: () => void }) { return <div className="content-card" role="alert"><h2>We couldn’t load your workspace.</h2><p className="subtle-copy">Your saved information is safe. Check your connection and try again.</p><button className="action-button" onClick={reset}>Try again</button></div>; }
