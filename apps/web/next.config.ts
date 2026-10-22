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
};

export default createNextIntlPlugin("./src/i18n/request.ts")(nextConfig);
