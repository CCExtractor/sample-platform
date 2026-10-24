import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { canManage, canOperateCi, getSession, login, logout, type Session } from "@/lib/auth";

const KEY = "sp-session";

function session(overrides: Partial<Session> = {}): Session {
  return {
    token: "tok",
    email: "dev@example.com",
    role: "user",
    expires_at: new Date(Date.now() + 60_000).toISOString(),
    ...overrides,
  };
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("getSession", () => {
  it("returns null when nothing is stored", () => {
    expect(getSession()).toBeNull();
  });

  it("drops an expired session", () => {
    localStorage.setItem(
      KEY,
      JSON.stringify(session({ expires_at: new Date(Date.now() - 1000).toISOString() })),
    );
    expect(getSession()).toBeNull();
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it("returns a still-valid session", () => {
    const s = session();
    localStorage.setItem(KEY, JSON.stringify(s));
    expect(getSession()).toEqual(s);
  });

  it("returns null for corrupt JSON", () => {
    localStorage.setItem(KEY, "{not-json");
    expect(getSession()).toBeNull();
  });
});

describe("role gates", () => {
  it("lets admins and contributors manage the suite", () => {
    expect(canManage(session({ role: "admin" }))).toBe(true);
    expect(canManage(session({ role: "contributor" }))).toBe(true);
    expect(canManage(session({ role: "tester" }))).toBe(false);
    expect(canManage(session({ role: "user" }))).toBe(false);
    expect(canManage(null)).toBe(false);
  });

  it("lets testers queue CI but not manage tests", () => {
    const tester = session({ role: "tester" });
    expect(canOperateCi(tester)).toBe(true);
    expect(canManage(tester)).toBe(false);
    expect(canOperateCi(session({ role: "user" }))).toBe(false);
  });
});

describe("login", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("stores the session after minting a token and reading /auth/me", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/auth/tokens") && init?.method === "POST") {
          return jsonResponse(200, {
            token: "minted",
            expires_at: "2099-01-01T00:00:00Z",
          });
        }
        if (url.endsWith("/auth/me")) {
          return jsonResponse(200, { role: "contributor" });
        }
        return jsonResponse(404, { message: "unexpected" });
      }),
    );

    const s = await login("dev@example.com", "secret");
    expect(s.token).toBe("minted");
    expect(s.role).toBe("contributor");
    expect(s.email).toBe("dev@example.com");
    expect(getSession()?.token).toBe("minted");
  });

  it("does not reveal whether the email exists on 401", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(401, { message: "no such user" })),
    );

    await expect(login("dev@example.com", "wrong")).rejects.toThrow(
      "Email or password is incorrect.",
    );
    expect(getSession()).toBeNull();
  });
});

describe("logout", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(204, {})),
    );
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { reload: vi.fn() },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("clears storage and reloads once even if called twice", async () => {
    localStorage.setItem(KEY, JSON.stringify(session()));
    logout();
    logout();
    await vi.waitFor(() => {
      expect(window.location.reload).toHaveBeenCalledTimes(1);
    });
    expect(localStorage.getItem(KEY)).toBeNull();
  });
});
