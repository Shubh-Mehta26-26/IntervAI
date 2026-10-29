import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  allowedDevOrigins: ["192.168.1.12"],
};

export default config;
