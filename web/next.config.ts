import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  serverExternalPackages: ["better-sqlite3"],
  experimental: { optimizePackageImports: ["framer-motion"] },
  poweredByHeader: false,
};

export default nextConfig;
