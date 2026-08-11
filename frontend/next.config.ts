import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Goi server.js + node_modules toi thieu vao .next/standalone. Stage `runner`
  // trong Dockerfile copy dung goi nay, nen bo dong nay se lam build hong:
  // khong co .next/standalone de COPY.
  output: "standalone",
};

export default nextConfig;
