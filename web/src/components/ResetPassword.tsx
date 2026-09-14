import { KeyRound, Loader2 } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { completePasswordReset } from "@/lib/api";
import { asset } from "@/lib/utils";

/**
 * Set a new password from the link in a recovery email.
 *
 * Reached without a session, so it renders on its own rather than inside
 * the shell. The three values in the query string are the platform's
 * signed link: they are handed straight back to the API, which is what
 * checks them. Nothing here can decide whether a link is good.
 */
export function ResetPassword() {
  const [params, setParams] = useState<{
    uid: number;
    expires: number;
    mac: string;
  } | null>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  // Read from the URL rather than the router: the link is built by the
  // platform's email template, and lands here under either history mode.
  useEffect(() => {
    const raw = window.location.href;
    const query = raw.slice(raw.indexOf("?") + 1);
    const q = new URLSearchParams(raw.includes("?") ? query : "");
    const uid = Number(q.get("uid"));
    const expires = Number(q.get("expires"));
    const mac = q.get("mac");
    if (uid && expires && mac) setParams({ uid, expires, mac });
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!params) return;
    setBusy(true);
    setError(null);
    try {
      await completePasswordReset({
        user_id: params.uid,
        expires: params.expires,
        mac: params.mac,
        password,
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "That did not work.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full items-center justify-center bg-background">
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
            <div className="text-[15px] font-semibold tracking-tight">
              Choose a new password
            </div>
            <div className="text-xs text-faint">CCExtractor Sample Platform</div>
          </div>
        </div>

        {!params && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/8 px-3 py-2 text-xs text-destructive">
            This link is missing part of itself. Ask for a new one from the sign-in
            page.
          </div>
        )}

        {params && !done && (
          <>
            <label
              htmlFor="reset-password"
              className="mb-1 block text-xs font-medium text-muted-foreground"
            >
              New password
            </label>
            <Input
              id="reset-password"
              type="password"
              value={password}
              autoComplete="new-password"
              onChange={(e) => setPassword(e.target.value)}
              className="mb-3"
            />
            <label
              htmlFor="reset-confirm"
              className="mb-1 block text-xs font-medium text-muted-foreground"
            >
              Repeat it
            </label>
            <Input
              id="reset-confirm"
              type="password"
              value={confirm}
              autoComplete="new-password"
              onChange={(e) => setConfirm(e.target.value)}
              className="mb-4"
            />
            {confirm && password !== confirm && (
              <div className="mb-3 text-[11px] text-destructive">
                The two do not match.
              </div>
            )}
            {error && (
              <div className="mb-3 rounded-lg border border-destructive/30 bg-destructive/8 px-3 py-2 text-xs text-destructive">
                {error}
              </div>
            )}
            <Button
              className="w-full"
              disabled={busy || !password || password !== confirm}
            >
              {busy ? <Loader2 className="animate-spin" /> : <KeyRound />} Set password
            </Button>
            {/* The link carries the old password's signature, so using it
                once is the last thing it can do. */}
            <p className="mt-4 text-center text-[11px] text-faint">
              This link works once, and stops working as soon as the password
              changes.
            </p>
          </>
        )}

        {done && (
          <>
            <div className="rounded-lg border border-success/30 bg-success/8 px-3 py-2 text-xs text-success">
              Password changed. You can sign in with it now.
            </div>
            <Button
              type="button"
              className="mt-4 w-full"
              onClick={() => {
                window.location.href = window.location.pathname;
              }}
            >
              Go to sign in
            </Button>
          </>
        )}
      </motion.form>
    </div>
  );
}
