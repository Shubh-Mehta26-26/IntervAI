"use client";
export default function ErrorPage({ reset }: { reset: () => void }) { return <div className="access-message" role="alert"><h2>We couldn’t connect right now.</h2><p>Please try again in a moment.</p><button className="action-button" onClick={reset}>Try again</button></div>; }
