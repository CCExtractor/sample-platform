import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Login } from "@/components/Login";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Login", () => {
  it("shows the same vague error on a 401", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(401, { message: "nope" })));

    render(<Login onDone={vi.fn()} />);
    await user.type(screen.getByLabelText("Email"), "dev@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText("Email or password is incorrect.")).toBeInTheDocument();
  });

  it("uses identical copy for a reset whether or not the address exists", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, { ok: true })));

    render(<Login onDone={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /forgot your password/i }));
    await user.type(screen.getByLabelText("Email"), "dev@example.com");
    await user.click(screen.getByRole("button", { name: /email me a reset link/i }));

    expect(
      await screen.findByText("If that address has an account, a reset link is on its way."),
    ).toBeInTheDocument();
  });

  it("calls onDone after a successful sign-in", async () => {
    const user = userEvent.setup();
    const onDone = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/auth/tokens")) {
          return jsonResponse(200, { token: "minted", expires_at: "2099-01-01T00:00:00Z" });
        }
        if (url.endsWith("/auth/me")) {
          return jsonResponse(200, { role: "user" });
        }
        return jsonResponse(404, {});
      }),
    );

    render(<Login onDone={onDone} />);
    await user.type(screen.getByLabelText("Email"), "dev@example.com");
    await user.type(screen.getByLabelText("Password"), "secret");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });
});
