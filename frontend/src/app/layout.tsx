import type { Metadata } from "next";
import "./globals.css";
import "./identity.css";
import "./intelligence.css";
import "./interviews.css";
import "./memory.css";
import "./learning.css";
import "./career.css";

export const metadata: Metadata = {
  title: "IntervAI · Your next chapter",
  description: "Your personal workspace for interview preparation and career growth.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
