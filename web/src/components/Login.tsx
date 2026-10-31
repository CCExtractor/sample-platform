import { Loader2, LogIn, Moon, Sun } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { requestPasswordReset, requestSignup } from "@/lib/api";
import { login } from "@/lib/auth";
import { asset } from "@/lib/utils";

const LINK = "cursor-pointer text-primary hover:underline";

type Mode = "signin" | "reset" | "signup";

const COPY: Record<Mode, { title: string; action: string; sent: string }> = {
  signin: { title: "", action: "", sent: "" },
  reset: {
    title: "Reset your password",
    action: "Email me a reset link",
    // Deliberately the same whether or not the address has an account: a
    // different answer here would tell an anonymous caller who is registered.
    sent: "If that address has an account, a reset link is on its way.",
  },
  signup: {
    title: "Create an account",
    action: "Email me a signup link",
    sent: "If that address can be registered, a signup link is on its way.",
  },
};

/** Full-screen sign-in against POST /api/v1/auth/tokens. */
export function Login({ onDone }: Readonly<{ onDone: () => void }>) {
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  const go = (next: Mode) => {
    setMode(next);
    setError(null);
    setSent(false);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "signin") {
        await login(email, password);
        onDone();
      } else {
        await (mode === "reset" ? requestPasswordReset : requestSignup)(email);
        setSent(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "That did not work.");
    } finally {
      setBusy(false);
    }
  };

  const [dark, setDark] = useState(() => localStorage.getItem("sp-theme") === "dark");
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("sp-theme", dark ? "dark" : "light");
  }, [dark]);

  return (
    <div className="relative flex h-full items-center justify-center bg-background">
      <button
        onClick={() => setDark(!dark)}
        aria-label="Toggle theme"
        className="absolute right-5 top-5 cursor-pointer rounded-lg border bg-card p-2 text-muted-foreground shadow-card transition-colors hover:text-foreground"
      >
        {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
      </button>
      <motion.form
        onSubmit={submit}
        className="w-full max-w-sm rounded-2xl border bg-card p-7 shadow-pop"
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
      >
        <div className="mb-6 flex items-center gap-3">
          <img src={asset("ccx.svg")} alt="CCExtractor" className="size-10" />
          <div>
            <div className="text-[15px] font-semibold tracking-tight">Sample Platform</div>
            <div className="text-xs text-faint">CCExtractor regression testing</div>
          </div>
        </div>

        {mode !== "signin" && (
          <div className="mb-4 text-[13px] font-medium">{COPY[mode].title}</div>
        )}

        <label htmlFor="signin-email" className="mb-1 block text-xs font-medium text-muted-foreground">
          Email
        </label>
        <Input
          id="signin-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          className="mb-3"
        />
        {mode === "signin" && (
          <>
            <label
              htmlFor="signin-password"
              className="mb-1 block text-xs font-medium text-muted-foreground"
            >
              Password
            </label>
            <Input
              id="signin-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mb-4"
            />
          </>
        )}
        {error && (
          <div className="mb-3 rounded-lg border border-destructive/30 bg-destructive/8 px-3 py-2 text-xs text-destructive">
            {error}
          </div>
        )}
        {sent && (
          <div className="mb-3 rounded-lg border border-success/30 bg-success/8 px-3 py-2 text-xs text-success">
            {COPY[mode].sent}
          </div>
        )}
        <Button
          className="w-full"
          disabled={busy || !email || (mode === "signin" && !password)}
        >
          {busy ? <Loader2 className="animate-spin" /> : <LogIn />}
          {mode === "signin" ? "Sign in" : COPY[mode].action}
        </Button>

        {/* Both links finish on the classic site, which is where accounts are
            created and passwords are set. */}
        <div className="mt-4 flex justify-center gap-3 text-[11px]">
          {mode === "signin" ? (
            <>
              <button type="button" onClick={() => go("reset")} className={LINK}>
                Forgot your password?
              </button>
              <span className="text-faint">·</span>
              <button type="button" onClick={() => go("signup")} className={LINK}>
                Create an account
              </button>
            </>
          ) : (
            <button type="button" onClick={() => go("signin")} className={LINK}>
              Back to sign in
            </button>
          )}
        </div>

        <p className="mt-3 text-center text-[11px] text-faint">
          Use the same account as the CCExtractor Sample Platform.
        </p>
      </motion.form>
    </div>
  );
}
