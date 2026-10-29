import type { Metadata } from "next";
import "./globals.css";
import "./identity.css";
import "./intelligence.css";
import "./interviews.css";
import "./memory.css";
import "./learning.css";
import "./career.css";
import "./design-system.css";
import "./avatar.css";
import "./interview-studio.css";
import "./editorial.css";
import "./interview-focus.css";
import "./aurora-glass.css";
import "./pearl-orb.css";
import { cookies } from "next/headers";
import { ThemeProvider } from "@/components/ui/theme";

export const metadata: Metadata = {
  title: "IntervAI · Prepare. Practice. Progress.",
  description: "Your personal workspace for interview preparation and career growth.",
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const theme = (await cookies()).get("intervai-theme")?.value === "dark" ? "dark" : "light";
  return <html lang="en" data-theme={theme}><body><ThemeProvider initialTheme={theme}>{children}</ThemeProvider></body></html>;
}
