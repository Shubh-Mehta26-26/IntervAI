"use client";
import { createContext, useContext, useEffect, useState } from "react";
import { Icon } from "./icon";
type Theme = "light" | "dark";
const ThemeContext = createContext({ theme: "light" as Theme, toggle: () => { } });
export function ThemeProvider({ initialTheme, children }: {
    initialTheme: Theme;
    children: React.ReactNode;
}) {
    const [theme, setTheme] = useState(initialTheme);
    useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
    function toggle() { const next = theme === "light" ? "dark" : "light"; document.documentElement.dataset.theme = next; document.cookie = `intervai-theme=${next}; Path=/; Max-Age=31536000; SameSite=Lax`; setTheme(next); }
    return <ThemeContext.Provider value={{ theme, toggle }}>{children}</ThemeContext.Provider>;
}
export function useTheme() { return useContext(ThemeContext); }
export function ThemeToggle() { const { theme, toggle } = useContext(ThemeContext); return <button type="button" className="icon-button theme-toggle" onClick={toggle} aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`} title={`Switch to ${theme === "light" ? "dark" : "light"} mode`}><Icon name={theme === "light" ? "moon" : "sun"}/></button>; }
