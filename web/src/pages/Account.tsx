import { useQueryClient } from "@tanstack/react-query";
import { ExternalLink, GitBranch, KeyRound, Loader2, UserRound, UserX } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm";
import { Input } from "@/components/ui/input";
import {
  deactivateUser,
  unlinkGithub,
  updateAccount,
  useGithubLink,
  useMe,
} from "@/lib/api";
import { logout, setSessionEmail } from "@/lib/auth";

/**
 * Your own account: name, email, password and closing it.
 *
 * Everything here is the caller acting on themselves, so it needs no role.
 * Administration of other people's accounts stays on the administration
 * page, where the rest of the platform's privileged actions live.
 */
export function Account() {
  const { data: me, isLoading } = useMe();

  return (
    <div className="mx-auto max-w-2xl px-6 py-6">
      <h1 className="mb-1 text-[15px] font-semibold tracking-tight">Your account</h1>
      <p className="mb-6 text-[13px] text-faint">
        {me ? (
          <>
            Signed in as <span className="font-medium text-muted-foreground">{me.email}</span> ·{" "}
            <span className="capitalize">{me.role}</span>
          </>
        ) : (
          "Loading your details…"
        )}
      </p>

      {isLoading && <div className="h-40 animate-pulse rounded-xl bg-muted/50" />}
      {me && (
        <div className="flex flex-col gap-6">
          <ProfileSection name={me.name} email={me.email} />
          <PasswordSection />
          <GithubSection />
          <CloseSection userId={me.user_id} />
        </div>
      )}
    </div>
  );
}

function ProfileSection({ name, email }: Readonly<{ name: string; email: string }>) {
  const qc = useQueryClient();
  const [draftName, setDraftName] = useState(name);
  const [draftEmail, setDraftEmail] = useState(email);
  const [current, setCurrent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // The query refetches after a save, so pick the server's values back up
  // rather than leaving whatever was typed sitting in the inputs.
  useEffect(() => {
    setDraftName(name);
    setDraftEmail(email);
  }, [name, email]);

  const emailChanged = draftEmail !== email;
  const nameChanged = draftName !== name;
  const dirty = emailChanged || nameChanged;
  // Both are required on the account, so an emptied field is a round trip
  // the server would only reject.
  const complete = draftName.trim() !== "" && draftEmail.trim() !== "";

  const save = async () => {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const patch: Parameters<typeof updateAccount>[0] = {};
      if (nameChanged) patch.name = draftName.trim();
      if (emailChanged) {
        patch.email = draftEmail.trim();
        patch.current_password = current;
      }
      await updateAccount(patch);
      setCurrent("");
      // The sidebar reads the email out of the stored session rather than
      // from the API, so it has to be told when this changes it.
      if (emailChanged) setSessionEmail(draftEmail.trim());
      await qc.invalidateQueries({ queryKey: ["me"] });
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <SectionLabel>
        <UserRound className="mr-1 inline size-3.5" /> Profile
      </SectionLabel>
      <div className="rounded-xl border bg-card p-4 shadow-card">
        <Field label="Display name">
          <Input value={draftName} onChange={(e) => setDraftName(e.target.value)} maxLength={50} />
        </Field>
        <Field label="Email">
          <Input
            type="email"
            value={draftEmail}
            onChange={(e) => setDraftEmail(e.target.value)}
          />
        </Field>
        {emailChanged && (
          <Field label="Current password">
            <Input
              type="password"
              value={current}
              autoComplete="current-password"
              onChange={(e) => setCurrent(e.target.value)}
              placeholder="required to change your email"
            />
          </Field>
        )}
        <div className="mt-3 flex items-center gap-3">
          <Button
            size="sm"
            disabled={busy || !dirty || !complete || (emailChanged && !current)}
            onClick={save}
          >
            {busy && <Loader2 className="animate-spin" />} Save profile
          </Button>
          {saved && !dirty && <span className="text-[11px] text-success">Saved.</span>}
          {error && <span className="text-[11px] text-destructive">{error}</span>}
        </div>
      </div>
    </section>
  );
}

function PasswordSection() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const mismatch = confirm.length > 0 && next !== confirm;

  const save = async () => {
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      await updateAccount({ current_password: current, new_password: next });
      setCurrent("");
      setNext("");
      setConfirm("");
      setDone(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <SectionLabel>
        <KeyRound className="mr-1 inline size-3.5" /> Password
      </SectionLabel>
      <div className="rounded-xl border bg-card p-4 shadow-card">
        <Field label="Current password">
          <Input
            type="password"
            value={current}
            autoComplete="current-password"
            onChange={(e) => setCurrent(e.target.value)}
          />
        </Field>
        <Field label="New password">
          <Input
            type="password"
            value={next}
            autoComplete="new-password"
            onChange={(e) => setNext(e.target.value)}
          />
        </Field>
        <Field label="Repeat new password">
          <Input
            type="password"
            value={confirm}
            autoComplete="new-password"
            onChange={(e) => setConfirm(e.target.value)}
          />
        </Field>
        {/* The minimum length lives in the platform's config, so the server
            is the one that reports it rather than a number copied here. */}
        <div className="mt-3 flex items-center gap-3">
          <Button
            size="sm"
            disabled={busy || !current || !next || next !== confirm}
            onClick={save}
          >
            {busy && <Loader2 className="animate-spin" />} Change password
          </Button>
          {mismatch && (
            <span className="text-[11px] text-destructive">The two do not match.</span>
          )}
          {done && !current && !next && (
            <span className="text-[11px] text-success">
              Password changed. This session stays signed in.
            </span>
          )}
          {error && <span className="text-[11px] text-destructive">{error}</span>}
        </div>
      </div>
    </section>
  );
}

/**
 * The GitHub connection, used for runs on your own forks and pull requests.
 *
 * Connecting is an OAuth redirect that finishes on the platform's classic
 * callback, so this sends you there and picks the result up afterwards
 * rather than handling the exchange itself.
 */
function GithubSection() {
  const qc = useQueryClient();
  const { data, isLoading } = useGithubLink();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const disconnect = async () => {
    setBusy(true);
    setError(null);
    try {
      await unlinkGithub();
      await qc.invalidateQueries({ queryKey: ["github-link"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <SectionLabel>
        <GitBranch className="mr-1 inline size-3.5" /> GitHub
      </SectionLabel>
      <div className="rounded-xl border bg-card p-4 shadow-card">
        {isLoading && <div className="h-8 animate-pulse rounded-md bg-muted/50" />}
        {data && (
          <>
            <p className="mb-3 text-[13px] text-muted-foreground">
              {data.linked ? (
                <>
                  Connected as{" "}
                  <span className="font-medium text-foreground">@{data.github_login}</span>.
                  Runs on your own forks and pull requests use this.
                </>
              ) : (
                <>
                  Not connected. Connecting lets the platform queue runs for your own
                  forks and pull requests.
                </>
              )}
            </p>
            {error && <div className="mb-2 text-[11px] text-destructive">{error}</div>}
            {data.linked ? (
              <Button size="sm" variant="outline" disabled={busy} onClick={disconnect}>
                {busy && <Loader2 className="animate-spin" />} Disconnect
              </Button>
            ) : (
              <a href={data.authorize_url} target="_blank" rel="noreferrer">
                <Button size="sm" variant="secondary">
                  <ExternalLink /> Connect to GitHub
                </Button>
              </a>
            )}
            {/* The redirect finishes on the classic site, so this page will
                not know about it until it is loaded again. */}
            <p className="mt-2 text-[11px] text-faint">
              {data.linked
                ? "Disconnecting only forgets the platform's copy. Withdraw the authorisation itself from your GitHub applications page."
                : "GitHub opens in a new tab. Reload this page once you are done there."}
            </p>
          </>
        )}
      </div>
    </section>
  );
}

function CloseSection({ userId }: Readonly<{ userId: number }>) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const go = async () => {
    setBusy(true);
    setError(null);
    try {
      await deactivateUser(userId);
      logout();
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work.");
      setBusy(false);
      setConfirming(false);
    }
  };

  return (
    <section className="pb-4">
      <SectionLabel>
        <UserX className="mr-1 inline size-3.5" /> Close account
      </SectionLabel>
      <div className="rounded-xl border border-destructive/30 bg-card p-4 shadow-card">
        <p className="mb-3 text-[13px] text-muted-foreground">
          Your name and email are replaced with a placeholder and the password is scrambled.
          The account itself stays so the samples and runs you own keep an author.
        </p>
        {error && <div className="mb-2 text-[11px] text-destructive">{error}</div>}
        <Button size="sm" variant="outline" className="text-destructive" onClick={() => setConfirming(true)}>
          <UserX /> Close my account
        </Button>
      </div>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Close your account?"
        body={
          <>
            You are signed out straight away and cannot sign back in.{" "}
            <b>This cannot be undone.</b> Ask an administrator if you need the account back.
          </>
        }
        confirmLabel={busy ? "Closing…" : "Close account"}
        busy={busy}
        onConfirm={go}
      />
    </section>
  );
}

function Field({ label, children }: Readonly<{ label: string; children: React.ReactNode }>) {
  return (
    <label className="mb-2.5 block">
      <span className="mb-1 block text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

function SectionLabel({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-faint">
      {children}
    </div>
  );
}
