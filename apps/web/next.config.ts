import path from "node:path";
import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";
import { parseEnv } from "./src/lib/env-schema";

// The monorepo keeps one .env at the root. Load it, then fail early with a readable message
// when a required public variable is missing.
loadEnvConfig(
  path.resolve(__dirname, "../.."),
  process.env.NODE_ENV !== "production",
  console,
  true,
);
parseEnv(process.env);

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  transpilePackages: ["@sg/contracts"],
  // People type /login out of habit; the page is /sign-in (the query string is kept).
  async redirects() {
    return [
      { source: "/login", destination: "/sign-in", permanent: false },
      { source: "/signin", destination: "/sign-in", permanent: false },
    ];
  },
};

export default createNextIntlPlugin("./src/i18n/request.ts")(nextConfig);
