import type { CSSProperties } from "react";
const paths: Record<string, string> = {
    search: "M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
    camera: "M3 6h12v12H3z M15 10l6-4v12l-6-4",
    cameraOff: "M3 3l18 18 M3 6h3 M10 6h5v4l6-4v12l-6-4 M15 18H3V6",
    expand: "M8 3H3v5 M16 3h5v5 M21 16v5h-5 M8 21H3v-5",
    mirror: "M12 3v18 M8 6L3 18h5z M16 6l5 12h-5z",
    grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z", user: "M20 21v-2a6 6 0 0 0-6-6h-4a6 6 0 0 0-6 6v2 M12 9a4 4 0 1 0 0-8 4 4 0 0 0 0 8", file: "M14 2H5v20h14V7z M14 2v6h5 M8 12h8 M8 16h6", briefcase: "M3 7h18v14H3z M8 7V3h8v4 M3 12a23 23 0 0 0 18 0 M12 11v4", mic: "M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0z M5 10v2a7 7 0 0 0 14 0v-2 M12 19v3 M8 22h8", chart: "M4 3v18h17 M8 16v-5 M13 16V7 M18 16v-9", book: "M12 5v16 M12 5C8 2 4 3 2 4v16c4-2 7-1 10 1 3-2 6-3 10-1V4c-2-1-6-2-10 1", target: "M21 12a9 9 0 1 1-9-9 M17 12a5 5 0 1 1-5-5 M12 12l9-9 M17 3h4v4", compass: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M16 8l-3 5-5 3 3-5z", arrow: "M5 12h14 M13 6l6 6-6 6", chevron: "M9 5l7 7-7 7", plus: "M12 5v14 M5 12h14", spark: "M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z", sun: "M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M12 1v2 M12 21v2 M1 12h2 M21 12h2 M4 4l2 2 M18 18l2 2 M4 20l2-2 M18 6l2-2", moon: "M21 13A9 9 0 1 1 11 3a7 7 0 0 0 10 10", menu: "M4 6h16 M4 12h16 M4 18h16", close: "M6 6l12 12 M18 6L6 18", shield: "M12 2l9 4v6c0 5-9 10-9 10S3 17 3 12V6z M8 12l3 3 5-6", check: "M5 12l4 4L19 6", code: "M8 6l-6 6 6 6 M16 6l6 6-6 6 M14 3l-4 18"
};
export function Icon({ name, size = 20, style }: {
    name: string;
    size?: number;
    style?: CSSProperties;
}) { return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style}><path d={paths[name] || paths.spark}/></svg>; }
