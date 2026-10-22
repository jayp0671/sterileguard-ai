import path from "node:path";

export const ROLES = [
  "technician",
  "supervisor",
  "dept_admin",
  "data_steward",
  "platform_admin",
] as const;
export type Role = (typeof ROLES)[number];

/** Storage state per role, written by global setup (gitignored). */
export const authFile = (role: Role) => path.join(__dirname, ".auth", `${role}.json`);

/**
 * Credentials come from env vars only, never from the repo:
 *   E2E_<ROLE>_EMAIL, E2E_<ROLE>_PASSWORD, E2E_<ROLE>_TOTP_SECRET
 * Users are created by `sg demo seed-demo` (SG-16).
 */
export function credentials(role: Role) {
  const key = role.toUpperCase();
  const email = process.env[`E2E_${key}_EMAIL`];
  const password = process.env[`E2E_${key}_PASSWORD`];
  const totpSecret = process.env[`E2E_${key}_TOTP_SECRET`];
  return email && password && totpSecret ? { email, password, totpSecret } : null;
}
