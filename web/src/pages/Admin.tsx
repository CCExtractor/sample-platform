import { useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Ban, FileX, FolderTree, KeyRound, ListOrdered, Mail, Plus, Tags, Trash2, UserX, Users, Wrench } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";

import { RunStatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm";
import {
  allowExtension,
  blockUser,
  createCategory,
  createTag,
  deactivateUser,
  deleteCategory,
  forbidExtension,
  renameCategory,
  revokeToken,
  sendUserReset,
  setMaintenance,
  unblockUser,
  updateUserRole,
  useBlockedUsers,
  useCategories,
  useForbiddenExtensions,
  useMaintenance,
  useQueue,
  useTags,
  useTokens,
  useUsers,
  type PlatformUser,
} from "@/lib/api";
import { getSession } from "@/lib/auth";
import { cn } from "@/lib/utils";
import type { RunStatus } from "@/lib/types";

const ROLES: PlatformUser["role"][] = ["admin", "contributor", "tester", "user"];

/**
 * Administration. Platform mutations live here and nowhere else — browse
 * pages stay read-only so a stray click can't change the suite.
 */
export function Admin() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-6">
      <h1 className="mb-1 text-[15px] font-semibold tracking-tight">Administration</h1>
      <p className="mb-6 text-[13px] text-faint">
        Manage users, categories, tags, CI availability and API tokens.
      </p>

      <div className="flex flex-col gap-6">
        <section>
          <SectionLabel>Regression suite</SectionLabel>
          <Link
            to="/tests/new"
            className="card-hover flex items-center gap-3 rounded-xl border bg-card p-4 shadow-card"
          >
            <span className="flex size-8 items-center justify-center rounded-lg bg-accent text-accent-foreground">
              <Plus className="size-4" />
            </span>
            <div>
              <div className="text-[13px] font-medium">New regression test</div>
              <div className="text-xs text-faint">
                Pick a sample, set the command, verify the output, then activate.
              </div>
            </div>
          </Link>
        </section>

        <UserSection />
        <CategorySection />
        <TagSection />
        <MaintenanceSection />
        <BlockedUsersSection />
        <ForbiddenSection />
        <QueueSection />
        <TokenSection />
      </div>
    </div>
  );
}

/**
 * Run one administration mutation and refresh its list. Every section here
 * needs the same busy/error handling, and a failed write must leave the list
 * showing what the server still has rather than an optimistic guess.
 */
function useMutate(queryKey: string) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: [queryKey] });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "That didn't work.");
    } finally {
      setBusy(false);
    }
  };

  return { run, busy, err };
}

function ErrorLine({ msg }: Readonly<{ msg: string | null }>) {
  if (!msg) return null;
  return <div className="mb-2 text-[11px] text-destructive">{msg}</div>;
}

function MaintenanceSection() {
  const { data } = useMaintenance();
  const { run, busy, err } = useMutate("maintenance");
  const platforms = data?.platforms ?? [];

  return (
    <section>
      <SectionLabel>
        <Wrench className="mr-1 inline size-3.5" /> Maintenance mode
      </SectionLabel>
      <ErrorLine msg={err} />
      <div className="grid grid-cols-2 gap-2">
        {platforms.map((m) => (
          <div
            key={m.platform}
            className="flex items-center justify-between rounded-xl border bg-card p-3.5 shadow-card"
          >
            <div>
              <div className="text-[13px] font-medium capitalize">{m.platform}</div>
              <div className="text-[11px] text-faint">
                {m.disabled ? "CI paused — new runs queue but won't start" : "Accepting runs"}
              </div>
            </div>
            <button
              disabled={busy}
              aria-label={m.disabled ? "Resume CI" : "Pause CI"}
              title={m.disabled ? "Resume CI" : "Pause CI"}
              onClick={() => run(() => setMaintenance(m.platform, !m.disabled))}
              className={cn(
                "relative h-5 w-9 cursor-pointer rounded-full transition-colors disabled:opacity-50",
                m.disabled ? "bg-warning" : "bg-border-strong",
              )}
            >
              <span
                className={cn(
                  "absolute top-0.5 size-4 rounded-full bg-white transition-transform",
                  m.disabled ? "translate-x-4" : "translate-x-0.5",
                )}
              />
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

function BlockedUsersSection() {
  const { data: blocked = [] } = useBlockedUsers();
  const { run, busy, err } = useMutate("blocked-users");
  const [id, setId] = useState("");
  const [comment, setComment] = useState("");

  const add = () =>
    run(async () => {
      await blockUser(Number(id), comment.trim() || "Blocked from the console");
      setId("");
      setComment("");
    });

  return (
    <section>
      <SectionLabel>
        <Ban className="mr-1 inline size-3.5" /> Blocked CI users
        <span className="ml-2 font-normal normal-case">{blocked.length}</span>
      </SectionLabel>
      <ErrorLine msg={err} />
      <div className="overflow-hidden rounded-xl border shadow-card">
        {blocked.map((b) => (
          <div
            key={b.user_id}
            className="flex items-center gap-3 border-b bg-card px-4 py-2 text-[13px] last:border-0"
          >
            <code className="font-medium">{b.user_id}</code>
            <span className="min-w-0 flex-1 truncate text-[11px] text-faint">{b.comment}</span>
            <Button
              variant="ghost"
              size="sm"
              className="text-destructive"
              disabled={busy}
              onClick={() => run(() => unblockUser(b.user_id))}
            >
              <Trash2 /> unblock
            </Button>
          </div>
        ))}
        <div className="flex items-center gap-2 bg-muted/30 px-3 py-2">
          {/* Numeric account id, not the login: GitHub logins can be changed
              and reused, which would silently unblock somebody. */}
          <input
            value={id}
            inputMode="numeric"
            onChange={(e) => setId(e.target.value.replace(/\D/g, ""))}
            placeholder="GitHub user id"
            className="h-7 w-32 rounded-md border bg-card px-2 font-mono text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="reason"
            className="h-7 flex-1 rounded-md border bg-card px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <Button size="sm" variant="secondary" disabled={busy || !id} onClick={add}>
            <Plus /> Block
          </Button>
        </div>
      </div>
    </section>
  );
}

function ForbiddenSection() {
  const { data: exts = [] } = useForbiddenExtensions();
  const { run, busy, err } = useMutate("forbidden-extensions");
  const [val, setVal] = useState("");

  return (
    <section>
      <SectionLabel>
        <FileX className="mr-1 inline size-3.5" /> Forbidden upload extensions
      </SectionLabel>
      <ErrorLine msg={err} />
      <div className="rounded-xl border bg-card p-3.5 shadow-card">
        <div className="flex flex-wrap gap-1.5">
          {exts.map((e) => (
            <span
              key={e}
              className="inline-flex items-center gap-1 rounded-md border bg-muted/60 px-2 py-0.5 font-mono text-[11px]"
            >
              .{e}
              <button
                disabled={busy}
                title={`Allow .${e} uploads again`}
                className="cursor-pointer text-faint hover:text-destructive disabled:opacity-50"
                onClick={() => run(() => allowExtension(e))}
              >
                ×
              </button>
            </span>
          ))}
          {exts.length === 0 && (
            <span className="text-[11px] text-faint">Every extension is accepted.</span>
          )}
        </div>
        <div className="mt-2.5 flex items-center gap-2">
          {/* Stored without the leading dot, alphanumeric only — the API
              rejects anything else so a pattern can't be smuggled in. */}
          <input
            value={val}
            onChange={(e) => setVal(e.target.value.replace(/[^a-z0-9]/gi, "").toLowerCase())}
            placeholder="extension"
            className="h-7 w-40 rounded-md border bg-card px-2 font-mono text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <Button
            size="sm"
            variant="secondary"
            disabled={busy || !val || exts.includes(val)}
            onClick={() => run(async () => { await forbidExtension(val); setVal(""); })}
          >
            <Plus /> Add
          </Button>
        </div>
      </div>
    </section>
  );
}

function CategorySection() {
  const { data: cats = [] } = useCategories();
  const { run, busy, err } = useMutate("categories");
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [fresh, setFresh] = useState("");

  // Enter commits and blurs, and Escape clears `editing` before the blur
  // lands — both would otherwise fire this twice, the second time undoing
  // the cancel.
  const commit = (id: number) => {
    if (editing !== id) return;
    const name = draft.trim();
    setEditing(null);
    if (name && name !== cats.find((c) => c.id === id)?.name) {
      run(() => renameCategory(id, name));
    }
  };

  return (
    <section>
      <SectionLabel>
        <FolderTree className="mr-1 inline size-3.5" /> Categories
        <span className="ml-2 font-normal normal-case">{cats.length}</span>
      </SectionLabel>
      <ErrorLine msg={err} />
      <div className="overflow-hidden rounded-xl border shadow-card">
        {cats.map((c) => (
          <div
            key={c.id}
            className="flex items-center gap-3 border-b bg-card px-4 py-2 text-[13px] last:border-0"
          >
            {editing === c.id ? (
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={() => commit(c.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commit(c.id);
                  if (e.key === "Escape") setEditing(null);
                }}
                className="h-7 flex-1 rounded-md border bg-card px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            ) : (
              <span className="font-medium">{c.name}</span>
            )}
            <span className="ml-auto text-[11px] text-faint">{c.test_count} tests</span>
            <Button
              variant="ghost"
              size="sm"
              disabled={busy}
              onClick={() => { setEditing(c.id); setDraft(c.name); }}
            >
              Rename
            </Button>
            {/* The API refuses with 409 while tests still reference it, so
                don't offer a click that can only fail. */}
            <Button
              variant="ghost"
              size="sm"
              className="text-destructive"
              disabled={busy || c.test_count > 0}
              title={
                c.test_count > 0
                  ? "Reassign its tests before deleting this category"
                  : "Delete category"
              }
              onClick={() => run(() => deleteCategory(c.id))}
            >
              <Trash2 />
            </Button>
          </div>
        ))}
        <div className="flex items-center gap-2 bg-muted/30 px-3 py-2">
          <input
            value={fresh}
            onChange={(e) => setFresh(e.target.value)}
            placeholder="new category name"
            className="h-7 flex-1 rounded-md border bg-card px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <Button
            size="sm"
            variant="secondary"
            disabled={busy || !fresh.trim()}
            onClick={() => run(async () => { await createCategory(fresh.trim()); setFresh(""); })}
          >
            <Plus /> Add
          </Button>
        </div>
      </div>
    </section>
  );
}

function TagSection() {
  const { data: tags = [] } = useTags();
  const { run, busy, err } = useMutate("tags");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const add = () =>
    run(async () => {
      await createTag(name.trim(), description.trim());
      setName("");
      setDescription("");
    });

  return (
    <section>
      <SectionLabel>
        <Tags className="mr-1 inline size-3.5" /> Sample tags
        <span className="ml-2 font-normal normal-case">{tags.length}</span>
      </SectionLabel>
      <ErrorLine msg={err} />
      <div className="overflow-hidden rounded-xl border shadow-card">
        {tags.map((t) => (
          <div
            key={t.id}
            className="flex items-center gap-3 border-b bg-card px-4 py-2 text-[13px] last:border-0"
          >
            <span className="font-medium">{t.name}</span>
            <span className="min-w-0 flex-1 truncate text-[11px] text-faint">
              {t.description || "no description"}
            </span>
          </div>
        ))}
        {/* Created here, applied to samples on the samples page. There is no
            removal: the classic site has no way to drop a tag either. */}
        <div className="flex items-center gap-2 bg-muted/30 px-3 py-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="tag name"
            className="h-7 w-40 rounded-md border bg-card px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="what it means"
            className="h-7 flex-1 rounded-md border bg-card px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <Button size="sm" variant="secondary" disabled={busy || !name.trim()} onClick={add}>
            <Plus /> Add
          </Button>
        </div>
      </div>
    </section>
  );
}

function UserSection() {
  const { data: users = [], isLoading } = useUsers();
  const qc = useQueryClient();
  const me = getSession();
  const [busy, setBusy] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<number | null>(null);
  const [closing, setClosing] = useState<PlatformUser | null>(null);

  // One runner for all three row actions: they share the per-row busy flag
  // and only the successful ones differ in what they leave behind.
  const act = async (u: PlatformUser, what: string, fn: () => Promise<unknown>) => {
    setBusy(u.user_id);
    setErr(null);
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ["users"] });
    } catch (e) {
      setErr(e instanceof Error ? e.message : `${what} failed`);
      return false;
    } finally {
      setBusy(null);
    }
    return true;
  };

  const changeRole = (u: PlatformUser, role: string) =>
    act(u, "Role change", () => updateUserRole(u.user_id, role));

  const sendReset = async (u: PlatformUser) => {
    setSentTo(null);
    if (await act(u, "Sending the reset link", () => sendUserReset(u.user_id))) {
      setSentTo(u.user_id);
    }
  };

  const deactivate = async () => {
    if (!closing) return;
    await act(closing, "Deactivation", () => deactivateUser(closing.user_id));
    setClosing(null);
  };

  return (
    <section>
      <SectionLabel>
        <Users className="mr-1 inline size-3.5" /> User management
        <span className="ml-2 font-normal normal-case">{users.length} users</span>
      </SectionLabel>
      {err && <div className="mb-2 text-[11px] text-destructive">{err}</div>}
      <div className="overflow-hidden rounded-xl border shadow-card">
        {isLoading && <div className="h-24 animate-pulse bg-muted/50" />}
        {users.map((u, i) => {
          const self = u.email === me?.email;
          return (
            <motion.div
              key={u.user_id}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: Math.min(i * 0.015, 0.3) }}
              className="flex items-center gap-3 border-b bg-card px-4 py-2 text-[13px] last:border-0"
            >
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium">
                  {u.name}
                  {self && <span className="ml-1.5 text-[10px] text-faint">(you)</span>}
                </div>
                <div className="truncate text-[11px] text-faint">{u.email}</div>
              </div>
              {sentTo === u.user_id && (
                <span className="text-[11px] text-success">reset link sent</span>
              )}
              {u.github_linked && <Badge variant="secondary">github</Badge>}
              <Button
                variant="ghost"
                size="sm"
                title="Email a password reset link to this account"
                disabled={busy === u.user_id}
                onClick={() => sendReset(u)}
              >
                <Mail />
              </Button>
              {/* Deactivating scrubs the name, email and password, so it is
                  a confirm; your own account is closed from the account page
                  instead, which signs you out afterwards. */}
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive"
                title={self ? "Close your own account from the account page" : "Deactivate this account"}
                disabled={self || busy === u.user_id}
                onClick={() => setClosing(u)}
              >
                <UserX />
              </Button>
              <select
                value={u.role}
                disabled={self || busy === u.user_id}
                onChange={(e) => changeRole(u, e.target.value)}
                className={cn(
                  "h-7 cursor-pointer rounded-md border bg-card px-2 text-xs capitalize shadow-card transition-colors hover:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  self && "cursor-not-allowed opacity-60",
                )}
                title={self ? "You can't change your own role" : "Change role"}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </motion.div>
          );
        })}
      </div>

      <ConfirmDialog
        open={closing !== null}
        onOpenChange={(o) => !o && setClosing(null)}
        title={`Deactivate ${closing?.name}?`}
        body={
          <>
            The name and email are replaced with a placeholder and the password is
            scrambled, so nobody can sign in as {closing?.email} again. The account row
            stays behind so their samples and runs keep an author.{" "}
            <b>This cannot be undone.</b>
          </>
        }
        confirmLabel={busy !== null ? "Deactivating…" : "Deactivate account"}
        busy={busy !== null}
        onConfirm={deactivate}
      />
    </section>
  );
}

function QueueSection() {
  const { data } = useQueue();
  return (
    <section>
      <SectionLabel>
        <ListOrdered className="mr-1 inline size-3.5" /> CI queue
        {data && (
          <span className="ml-2 font-normal normal-case">
            {data.meta.running_count} running · {data.meta.queue_depth} queued
          </span>
        )}
      </SectionLabel>
      <div className="overflow-hidden rounded-xl border shadow-card">
        {(data?.data ?? []).map((q) => (
          <div
            key={q.run_id}
            className="flex items-center gap-3 border-b bg-card px-4 py-2.5 text-[13px] last:border-0"
          >
            <code className="text-xs text-faint">run {q.run_id}</code>
            <span className="text-xs uppercase tracking-wider text-muted-foreground">
              {q.platform}
            </span>
            <RunStatusBadge status={q.status as RunStatus} className="ml-auto" />
          </div>
        ))}
        {data?.data.length === 0 && (
          <div className="bg-card px-4 py-6 text-center text-xs text-faint">Queue is empty.</div>
        )}
      </div>
    </section>
  );
}

function TokenSection() {
  const { data: tokens = [], isLoading } = useTokens();
  const qc = useQueryClient();
  const [revoking, setRevoking] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const current = getSession();

  const doRevoke = async () => {
    if (revoking === null) return;
    setBusy(true);
    try {
      await revokeToken(revoking);
      await qc.invalidateQueries({ queryKey: ["tokens"] });
    } finally {
      setBusy(false);
      setRevoking(null);
    }
  };

  const active = tokens.filter((t) => !t.is_revoked);

  return (
    <section>
      <SectionLabel>
        <KeyRound className="mr-1 inline size-3.5" /> API tokens
        <span className="ml-2 font-normal normal-case">{active.length} active</span>
      </SectionLabel>
      <div className="overflow-hidden rounded-xl border shadow-card">
        {isLoading && <div className="h-20 animate-pulse bg-muted/50" />}
        {active.map((t, i) => (
          <motion.div
            key={t.id}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: i * 0.03 }}
            className="flex items-center gap-3 border-b bg-card px-4 py-2.5 text-[13px] last:border-0"
          >
            <code className="text-xs">{t.token_prefix}…</code>
            <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
              {t.token_name}
            </span>
            <span className="hidden gap-1 md:flex">
              {t.scopes.slice(0, 3).map((s) => (
                <Badge key={s} variant="secondary">{s}</Badge>
              ))}
              {t.scopes.length > 3 && <Badge variant="secondary">+{t.scopes.length - 3}</Badge>}
            </span>
            <span className="text-[11px] text-faint">
              expires {new Date(t.expires_at).toLocaleDateString()}
            </span>
            <Button
              variant="ghost"
              size="sm"
              className="text-destructive"
              onClick={() => setRevoking(t.id)}
            >
              <Trash2 /> revoke
            </Button>
          </motion.div>
        ))}
      </div>

      <ConfirmDialog
        open={revoking !== null}
        onOpenChange={(o) => !o && setRevoking(null)}
        title="Revoke this API token?"
        body={
          <>
            Anything using it loses access immediately.
            {current && " Revoking the token this session uses signs you out."}
          </>
        }
        confirmLabel={busy ? "Revoking…" : "Revoke token"}
        busy={busy}
        onConfirm={doRevoke}
      />
    </section>
  );
}

function SectionLabel({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-faint">
      {children}
    </div>
  );
}
