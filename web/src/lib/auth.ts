// Session handling. Login mints a bearer token via POST /auth/tokens, then
// asks /auth/me for the server-side role. The role only gates what the UI
// shows — every mutation is re-checked on the server.

export type Role = "user" | "tester" | "contributor" | "admin";

export interface Session {
  token: string;
  email: string;
  role: Role;
  expires_at: string;
}

const KEY = "sp-session";

// Every role needs runs:write (fork runs are open to any signed-in user);
// the write scopes that actually matter — baseline replacement and token
// administration — are only minted once /auth/me confirms a role that can
// use them. Keeps the stored token boring for everyone else.
//
// Only admins may request the elevated set: the API rejects those scopes for
// every other role at mint time, and the endpoints behind them (baseline
// approval, user administration, platform configuration) are admin-only
// anyway. Contributors edit the suite with runs:write, already in the base set.
const BASE_SCOPES = ["runs:read", "runs:write", "results:read", "system:read"];
const ELEVATED_SCOPES = [
  ...BASE_SCOPES,
  "baselines:write",
  "tokens:manage",
  "system:write",
];

export function getSession(): Session | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as Session;
    if (new Date(s.expires_at) < new Date()) {
      localStorage.removeItem(KEY);
      return null;
    }
    return s;
  } catch {
    return null;
  }
}

export function canManage(s: Session | null): boolean {
  return s?.role === "admin" || s?.role === "contributor";
}

/** Roles allowed to queue/cancel CI runs (mirrors the API's require_roles). */
export function canOperateCi(s: Session | null): boolean {
  return s?.role === "admin" || s?.role === "contributor" || s?.role === "tester";
}

interface TokenResponse {
  token: string;
  expires_at: string;
}

async function mintToken(email: string, password: string, scopes: string[]): Promise<TokenResponse> {
  const res = await fetch("/api/v1/auth/tokens", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      password,
      token_name: `web-console-${crypto.randomUUID().slice(0, 8)}`,
      scopes,
    }),
  });
  if (!res.ok) {
    // Deliberately vague on auth failures — precise reasons enable account
    // enumeration. The server's message still lands in the console.
    const body = await res.json().catch(() => ({}));
    console.warn("login failed:", res.status, body.message ?? res.statusText);
    throw new Error(
      res.status === 401 || res.status === 403
        ? "Email or password is incorrect."
        : "Sign-in failed — try again in a moment.",
    );
  }
  return res.json();
}

async function revokeOnServer(token: string): Promise<void> {
  try {
    await fetch("/api/v1/auth/tokens/current", {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    // Offline or server down — the token still dies at its server-side expiry.
  }
}

export async function login(email: string, password: string): Promise<Session> {
  let minted = await mintToken(email, password, BASE_SCOPES);

  // Fetch the role the server actually assigned to this account.
  const meRes = await fetch("/api/v1/auth/me", {
    headers: { Authorization: `Bearer ${minted.token}` },
  });
  const me = meRes.ok ? await meRes.json() : { role: "user" };
  const role = (me.role as Role) ?? "user";

  if (role === "admin") {
    // Swap the probe token for a write-capable one; the probe is revoked
    // either way so a failed upgrade doesn't leave it behind.
    const probe = minted.token;
    try {
      minted = await mintToken(email, password, ELEVATED_SCOPES);
      revokeOnServer(probe);
    } catch (e) {
      // Keep the working base-scope session rather than failing the sign-in;
      // admin-only actions will surface a permission error if it comes to it.
      console.warn("elevated token mint failed, continuing with base scopes:", e);
    }
  }

  const session: Session = {
    token: minted.token,
    email,
    role,
    expires_at: minted.expires_at,
  };
  localStorage.setItem(KEY, JSON.stringify(session));
  return session;
}

/** Fired when the stored session changes under a mounted shell. */
export const SESSION_CHANGED = "sp-session-changed";

/** Keep the cached session in step once the account's email changes. */
export function setSessionEmail(email: string) {
  const s = getSession();
  if (!s) return;
  localStorage.setItem(KEY, JSON.stringify({ ...s, email }));
  window.dispatchEvent(new Event(SESSION_CHANGED));
}

let loggingOut = false;

export function logout() {
  // Parallel queries all hit 401 at once when a token dies — only the first
  // caller gets to tear the session down and reload.
  if (loggingOut) return;
  loggingOut = true;
  const s = getSession();
  localStorage.removeItem(KEY);
  const done = () => window.location.reload();
  if (s) revokeOnServer(s.token).finally(done);
  else done();
}
