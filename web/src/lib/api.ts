// Data layer. Everything here is live: the bundled snapshot that used to
// fill in per-test history now only backs demo mode, which patches fetch in
// lib/demo.ts and never reaches this file.

import { useQuery } from "@tanstack/react-query";

import { getSession, logout } from "@/lib/auth";
import type {
  LiveRun,
  LogicalRun,
  Platform,
  RegressionTest,
  RunSummary,
  Sample,
  SparkResult,
} from "@/lib/types";

/* ---------------- live fetch helpers ---------------- */

const BASE = "/api/v1";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/**
 * Turn an API failure into copy safe to render. 4xx validation messages are
 * written for end users and pass through; auth failures and server errors
 * get generic copy so backend internals never reach the screen. The raw
 * message goes to the console either way.
 */
function apiError(status: number, raw: string): ApiError {
  console.warn(`API ${status}:`, raw);
  if (status === 401) return new ApiError(status, "Session expired — sign in again.");
  if (status === 403) return new ApiError(status, "You don't have permission to do that.");
  if (status === 429) return new ApiError(status, "Rate limited — give it a minute.");
  if (status >= 500) return new ApiError(status, "The platform hit an internal error. Try again shortly.");
  return new ApiError(status, raw || "Request failed.");
}

async function apiGet<T>(path: string): Promise<T> {
  const session = getSession();
  const res = await fetch(`${BASE}${path}`, {
    headers: session ? { Authorization: `Bearer ${session.token}` } : {},
  });
  if (res.status === 401 && session) {
    // Token expired/revoked server-side — drop the stale session and land
    // back on the login screen instead of erroring every query. logout()
    // guards itself against the parallel-query stampede.
    logout();
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw apiError(res.status, body.message ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

async function apiSend<T>(method: string, path: string, body: unknown): Promise<T> {
  const session = getSession();
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(session ? { Authorization: `Bearer ${session.token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (res.status === 401 && session) logout();
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw apiError(res.status, data.message ?? res.statusText);
  return data as T;
}

interface Envelope<T> {
  data: T[];
  pagination?: { total: number; next_offset: number | null };
}

/** Follow offset pagination until exhausted (API caps limit at 100). */
async function fetchAll<T>(path: string, cap = 500): Promise<T[]> {
  const sep = path.includes("?") ? "&" : "?";
  const out: T[] = [];
  let offset = 0;
  for (;;) {
    const page = await apiGet<Envelope<T>>(`${path}${sep}limit=100&offset=${offset}`);
    out.push(...page.data);
    const next = page.pagination?.next_offset ?? null;
    if (next === null || out.length >= cap || page.data.length === 0) break;
    offset = next;
  }
  return out;
}

/* ---------------- live queries ---------------- */

/** How many past runs the sparklines and the average runtime look back over. */
const HISTORY_RUNS = 6;

interface TestHistory {
  recent_results: SparkResult[];
  avg_runtime_ms: number | null;
}

/**
 * A run that skipped this test leaves a gap in the series rather than a
 * failure, which is what customized runs produce.
 */
function sparkResultOf(status: string): SparkResult {
  if (status === "pass") return "pass";
  if (status === "fail") return "fail";
  return "skip";
}

/** Collect one test's results and runtimes across the runs that covered it. */
function foldRunRows(perRun: RunSampleRow[][]) {
  const history = new Map<number, TestHistory>();
  const runtimes = new Map<number, number[]>();

  for (const row of perRun.flat()) {
    const entry = history.get(row.regression_test_id) ?? {
      recent_results: [],
      avg_runtime_ms: null,
    };
    entry.recent_results.push(sparkResultOf(row.status));
    history.set(row.regression_test_id, entry);

    if (row.runtime_ms != null) {
      runtimes.set(row.regression_test_id, [
        ...(runtimes.get(row.regression_test_id) ?? []),
        row.runtime_ms,
      ]);
    }
  }

  for (const [id, times] of runtimes) {
    const entry = history.get(id);
    if (entry && times.length > 0) {
      entry.avg_runtime_ms = times.reduce((a, b) => a + b, 0) / times.length;
    }
  }
  return history;
}

/**
 * Per-test result history, assembled from recent runs.
 *
 * There is no per-test history endpoint, but /runs/{id}/samples already
 * returns every test's status and runtime for one run, so reading a handful
 * of runs and transposing them costs a few requests rather than one per
 * test. Only commit runs count: a PR run failing says something about the
 * pull request, not about the health of the test.
 */
export function useTestHistory() {
  const { data: runs = [] } = useRuns();
  const runIds = runs
    .filter((r) => r.test_type === "commit")
    .slice(0, HISTORY_RUNS)
    .flatMap((r) => r.platforms.map((p) => p.run_id))
    .toSorted((a, b) => a - b);

  return useQuery({
    queryKey: ["test-history", runIds],
    enabled: runIds.length > 0,
    staleTime: 60_000,
    queryFn: async () =>
      foldRunRows(
        await Promise.all(
          runIds.map((id) => fetchAll<RunSampleRow>(`/runs/${id}/samples`, 400)),
        ),
      ),
  });
}

interface RunSampleRow {
  regression_test_id: number;
  status: string;
  runtime_ms: number | null;
}

/** Regression tests: the live list, with history and sha joined in. */
export function useRegressionTests() {
  const { data: history } = useTestHistory();
  const { data: samples = [] } = useSamples();

  const rows = useQuery({
    queryKey: ["regression-tests"],
    staleTime: 60_000,
    queryFn: async () => {
      const [act, inact] = await Promise.all([
        fetchAll<LiveRegressionTest>("/regression-tests?active=true"),
        fetchAll<LiveRegressionTest>("/regression-tests?active=false"),
      ]);
      return [...act, ...inact].sort(
        (a, b) => a.regression_test_id - b.regression_test_id,
      );
    },
  });

  const shaById = new Map(samples.map((s) => [s.id, s.sha]));
  const data = (rows.data ?? []).map((r): RegressionTest => {
    const past = history?.get(r.regression_test_id);
    return {
      id: r.regression_test_id,
      sample_id: r.sample_id,
      sample_name: r.sample_name,
      sample_sha: shaById.get(r.sample_id) ?? "",
      command: r.command,
      input_type: r.input_type,
      output_type: r.output_type,
      expected_rc: r.expected_rc,
      active: r.active,
      description: r.description ?? "",
      categories: r.categories,
      avg_runtime_ms: past?.avg_runtime_ms ?? null,
      recent_results: past?.recent_results ?? [],
    };
  });

  return { data, isLoading: rows.isLoading };
}

/**
 * Where a file lives, rather than the file itself.
 *
 * Samples and baselines are handed out as signed URLs so large transfers do
 * not run through the API. A null download_url means the only copy is on the
 * platform's own disk and there is nothing to link to.
 */
export interface StoredFile {
  filename: string;
  download_url: string | null;
  storage_status: "ok" | "degraded";
}

export const sampleFile = (sampleId: number) =>
  apiGet<StoredFile>(`/samples/${sampleId}/download`);

export const baselineFile = (testId: number, outputId: number) =>
  apiGet<StoredFile>(`/regression-tests/${testId}/outputs/${outputId}/download`);

export const variantFile = (testId: number, outputId: number, variantId: number) =>
  apiGet<StoredFile>(
    `/regression-tests/${testId}/outputs/${outputId}/variants/${variantId}/download`,
  );

/** One test with its baselines, which the list endpoint leaves out. */
export function useRegressionTestDetail(id: number | null) {
  return useQuery({
    queryKey: ["regression-test", id],
    enabled: id !== null,
    staleTime: 60_000,
    queryFn: () => apiGet<RegressionTestDetail>(`/regression-tests/${id}`),
  });
}

export interface RegressionTestOutputDetail {
  id: number;
  correct: string;
  correct_extension: string;
  expected_filename: string | null;
  ignore: boolean;
  variants: { id: number; hash: string }[];
}

interface RegressionTestDetail {
  regression_test_id: number;
  outputs: RegressionTestOutputDetail[];
}

interface LiveRegressionTest {
  regression_test_id: number;
  sample_id: number;
  sample_name: string;
  command: string;
  input_type: string | null;
  output_type: string | null;
  expected_rc: number;
  active: boolean;
  description: string | null;
  categories: string[];
}

export function useSamples() {
  return useQuery({
    queryKey: ["samples"],
    staleTime: 60_000,
    queryFn: async () => {
      const res = await fetchAll<LiveSample>("/samples");
      return res.map(
        (s): Sample => ({
          id: s.sample_id,
          sha: s.sha,
          extension: s.extension.startsWith(".") ? s.extension : `.${s.extension}`,
          original_name: s.original_name,
          tags: s.tags ?? [],
          test_count: s.regression_test_count ?? 0,
        }),
      );
    },
  });
}

interface LiveSample {
  sample_id: number;
  sha: string;
  extension: string;
  original_name: string;
  tags: string[];
  regression_test_count: number;
}

/** Runs, grouped client-side into logical (per-commit) entries. */
export function useRuns() {
  return useQuery({
    queryKey: ["runs"],
    staleTime: 30_000,
    refetchInterval: 30_000,
    queryFn: async () => {
      const res = await apiGet<Envelope<LiveRun>>("/runs?limit=40&sort=-created_at");
      const groups = new Map<string, LiveRun[]>();
      for (const r of res.data) {
        const key = `${r.commit_sha}:${r.pr_number ?? ""}`;
        groups.set(key, [...(groups.get(key) ?? []), r]);
      }
      const logical: LogicalRun[] = [...groups.values()].map((g) => {
        const first = g[0];
        return {
          id: String(Math.max(...g.map((x) => x.run_id))),
          commit: first.commit_sha.slice(0, 9),
          branch: first.branch,
          fork: first.repository,
          pr_nr: first.pr_number,
          test_type: first.test_type,
          created_at: first.created_at,
          github_link: first.github_link,
          platforms: g
            .toSorted((a, b) => a.platform.localeCompare(b.platform))
            .map((x) => ({
              run_id: x.run_id,
              platform: x.platform,
              status: x.status,
              started_at: x.started_at,
              completed_at: x.completed_at,
            })),
        };
      });
      return logical.toSorted((a, b) => Number(b.id) - Number(a.id));
    },
  });
}

/** Single run (one platform) — GET /runs/<id>. */
export function useRun(runId: number | null) {
  return useQuery({
    queryKey: ["run", runId],
    enabled: runId !== null,
    queryFn: () => apiGet<LiveRun>(`/runs/${runId}`),
  });
}

export interface ProgressEvent {
  status: string;
  message: string;
  timestamp: string;
}

export function useRunProgress(runId: number | null) {
  return useQuery({
    queryKey: ["run-progress", runId],
    enabled: runId !== null,
    refetchInterval: (q) => {
      const data = q.state.data as ProgressEvent[] | undefined;
      const done = data?.some((e) => e.status === "completed" || e.status === "canceled");
      return done ? false : 15_000; // poll live runs, stop once finished
    },
    queryFn: async () => {
      const res = await apiGet<Envelope<ProgressEvent>>(`/runs/${runId}/progress`);
      return res.data;
    },
  });
}

/** Every result row of a run (all statuses) — GET /runs/<id>/samples. */
export function useRunSamples(runId: number | null) {
  return useQuery({
    queryKey: ["run-samples-all", runId],
    enabled: runId !== null,
    staleTime: 120_000,
    queryFn: () => fetchAll<RunFailure>(`/runs/${runId}/samples`, 400),
  });
}

/** Per-run counts, fetched lazily when a run row expands. */
export function useRunSummary(runId: number | null) {
  return useQuery({
    queryKey: ["run-summary", runId],
    enabled: runId !== null,
    staleTime: 300_000,
    queryFn: () => apiGet<RunSummary>(`/runs/${runId}/summary`),
  });
}

/** One failing result row from GET /runs/<id>/samples?status=fail. */
export interface RunFailure {
  regression_test_id: number;
  sample_id: number;
  sample_name: string;
  command: string;
  categories: string[];
  status: string;
  exit_code: number | null;
  expected_rc: number | null;
  runtime_ms: number | null;
  outputs: { output_id: number; filename: string; status: string }[];
}

/** Live failures for a platform run (used by triage + run expansion). */
export function useRunFailures(runId: number | null) {
  return useQuery({
    queryKey: ["run-failures", runId],
    enabled: runId !== null,
    staleTime: 300_000,
    queryFn: () => fetchAll<RunFailure>(`/runs/${runId}/samples?status=fail`, 300),
  });
}

export interface QueueEntry {
  run_id: number;
  platform: Platform;
  status: string;
  position: number | null;
  queued_at: string | null;
  started_at: string | null;
}

export function useQueue() {
  return useQuery({
    queryKey: ["queue"],
    refetchInterval: 30_000,
    queryFn: async () => {
      const session = getSession();
      const res = await fetch(`${BASE}/system/queue`, {
        headers: session ? { Authorization: `Bearer ${session.token}` } : {},
      });
      if (!res.ok) throw apiError(res.status, res.statusText);
      const body = (await res.json()) as {
        data: QueueEntry[];
        meta: { queue_depth: number; running_count: number };
      };
      return body;
    },
  });
}

export interface ApiToken {
  id: number;
  token_name: string;
  token_prefix: string;
  scopes: string[];
  created_at: string;
  expires_at: string;
  is_revoked: boolean;
}

export function useTokens() {
  return useQuery({
    queryKey: ["tokens"],
    queryFn: async () => {
      const res = await apiGet<Envelope<ApiToken>>("/auth/tokens");
      return res.data;
    },
  });
}

export async function revokeToken(id: number): Promise<void> {
  const session = getSession();
  const res = await fetch(`${BASE}/auth/tokens/${id}`, {
    method: "DELETE",
    headers: session ? { Authorization: `Bearer ${session.token}` } : {},
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw apiError(res.status, body.message ?? res.statusText);
  }
}

export interface HistoryEntry {
  run_id: number;
  regression_test_id: number;
  platform: Platform;
  status: string;
  commit_sha: string;
  branch: string;
  tested_at: string | null;
}

export interface MediaInfoNode {
  name: string;
  value: string | Record<string, string> | { name: string; value: Record<string, string> }[];
}

export interface SampleDetails {
  sample_id: number;
  sha: string;
  extension: string;
  original_name: string;
  filename: string;
  tags: string[];
  upload: {
    platform: string | null;
    parameters: string;
    notes: string;
    version: string | null;
    version_released: string | null;
  } | null;
  extra_files: { id: number; original_name: string; extension: string }[];
  media_info: MediaInfoNode[] | null;
}

export function useSampleDetails(sampleId: number | null) {
  return useQuery({
    queryKey: ["sample-details", sampleId],
    enabled: sampleId !== null,
    staleTime: 300_000,
    queryFn: () => apiGet<SampleDetails>(`/samples/${sampleId}/details`),
  });
}

export function useSampleHistory(sampleId: number | null) {
  return useQuery({
    queryKey: ["sample-history", sampleId],
    enabled: sampleId !== null,
    staleTime: 300_000,
    queryFn: async () => {
      // Keep the query date-bounded: without created_after the endpoint
      // loads every historical run before paginating, which takes ~10s on
      // a long-lived sample. 45 days covers anything worth triaging.
      const since = new Date(Date.now() - 45 * 86_400_000).toISOString().slice(0, 10);
      const res = await apiGet<Envelope<HistoryEntry>>(
        `/samples/${sampleId}/history?limit=20&created_after=${since}`,
      );
      return res.data;
    },
  });
}

/**
 * Promote a run's actual output to the expected baseline. This replaces the
 * stored hash for every future run, so the UI must confirm before calling.
 * Admin-only and applied immediately — the server enforces admin role +
 * baselines:write.
 */
export async function promoteBaseline(args: {
  runId: number;
  sampleId: number;
  regressionId: number;
  outputId: number;
}): Promise<{ ok: boolean; message: string }> {
  const session = getSession();
  const res = await fetch(
    `${BASE}/runs/${args.runId}/samples/${args.sampleId}/baseline-approval`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(session ? { Authorization: `Bearer ${session.token}` } : {}),
      },
      body: JSON.stringify({
        regression_id: args.regressionId,
        output_id: args.outputId,
        remove_variants: false,
      }),
    },
  );
  const body = await res.json().catch(() => ({}));
  return {
    ok: res.ok,
    message: body.message ?? (res.ok ? "Baseline promoted." : res.statusText),
  };
}

export interface PlatformUser {
  user_id: number;
  name: string;
  email: string;
  role: "admin" | "contributor" | "tester" | "user";
  github_linked: boolean;
  github_login: string | null;
}

export function useUsers() {
  // Paged: the platform has hundreds of accounts, and a single page would
  // silently show the first 50 as if that were everyone.
  return useQuery({
    queryKey: ["users"],
    queryFn: () => fetchAll<PlatformUser>("/users"),
  });
}

export function updateUserRole(id: number, role: string) {
  return apiSend<PlatformUser>("PATCH", `/users/${id}`, { role });
}

/* ---------------- administration ---------------- */

const apiDelete = <T,>(path: string) => apiSend<T>("DELETE", path, undefined);

export interface LiveCategory {
  id: number;
  name: string;
  description: string;
  test_count: number;
}

export function useCategories() {
  return useQuery({
    queryKey: ["categories"],
    queryFn: () => fetchAll<LiveCategory>("/categories"),
  });
}

export const createCategory = (name: string) =>
  apiSend<LiveCategory>("POST", "/categories", { name });

export const renameCategory = (id: number, name: string) =>
  apiSend<LiveCategory>("PATCH", `/categories/${id}`, { name });

/** Refused with 409 while any regression test still references the category. */
export const deleteCategory = (id: number) =>
  apiDelete<{ id: number; deleted: boolean }>(`/categories/${id}`);

export interface MaintenanceState {
  platform: Platform;
  disabled: boolean;
}

export function useMaintenance() {
  return useQuery({
    queryKey: ["maintenance"],
    queryFn: () => apiGet<{ platforms: MaintenanceState[] }>("/system/maintenance"),
  });
}

export const setMaintenance = (platform: Platform, disabled: boolean) =>
  apiSend<MaintenanceState>("PATCH", `/system/maintenance/${platform}`, { disabled });

export interface BlockedUser {
  user_id: number;
  comment: string;
}

export function useBlockedUsers() {
  return useQuery({
    queryKey: ["blocked-users"],
    queryFn: () => fetchAll<BlockedUser>("/system/blocked-users"),
  });
}

/** Keyed on the numeric GitHub account id — logins can be changed and reused. */
export const blockUser = (userId: number, comment: string) =>
  apiSend<BlockedUser>("POST", "/system/blocked-users", {
    user_id: userId,
    comment,
  });

export const unblockUser = (userId: number) =>
  apiDelete<{ user_id: number }>(`/system/blocked-users/${userId}`);

export function useForbiddenExtensions() {
  return useQuery({
    queryKey: ["forbidden-extensions"],
    queryFn: () => fetchAll<string>("/system/forbidden-extensions"),
  });
}

export const forbidExtension = (extension: string) =>
  apiSend<{ extension: string }>("POST", "/system/forbidden-extensions", {
    extension,
  });

export const allowExtension = (extension: string) =>
  apiDelete<{ extension: string }>(`/system/forbidden-extensions/${extension}`);

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    staleTime: 60_000,
    queryFn: () =>
      apiGet<{ status: string; dependencies: { name: string; status: string }[] }>(
        "/system/health",
      ),
  });
}

/* ---------------- write operations (live) ---------------- */

export interface RegressionTestPatch {
  command?: string;
  description?: string;
  expected_rc?: number;
  active?: boolean;
  categories?: string[];
}

export function updateRegressionTest(id: number, patch: RegressionTestPatch) {
  return apiSend<unknown>("PATCH", `/regression-tests/${id}`, patch);
}

export function createRegressionTest(body: {
  sample_id: number;
  command: string;
  input_type?: string;
  output_type?: string;
  expected_rc?: number;
  description?: string;
  categories: string[];
}) {
  return apiSend<{ regression_test_id: number }>("POST", "/regression-tests", body);
}

/** Queue a real CI run (old "customized tests"). One call per platform. */
export function createRun(body: {
  commit_sha: string;
  platform: Platform;
  branch?: string;
  repository: string;
  regression_test_ids?: number[];
}) {
  return apiSend<{ run_id: number }>("POST", "/runs", body);
}

/** Cancel a queued/running run. Idempotent — a finished run returns no_op. */
export function cancelRun(runId: number, reason?: string) {
  return apiSend<{ run_id: number; status: string; message: string }>(
    "POST",
    `/runs/${runId}/cancel`,
    reason ? { reason } : {},
  );
}

/** One artifact of a finished run: build log, expected/actual outputs. */
export interface RunArtifact {
  artifact_id: string;
  run_id: number;
  sample_id: number | null;
  type: string;
  filename: string;
  content_type: string | null;
  size_bytes: number | null;
  storage_status: string;
  download_url: string | null;
}

export function useRunArtifacts(runId: number | null) {
  return useQuery({
    queryKey: ["run-artifacts", runId],
    enabled: runId !== null,
    staleTime: 300_000,
    queryFn: () => fetchAll<RunArtifact>(`/runs/${runId}/artifacts`, 200),
  });
}

/**
 * Fetch a run's whole build log and hand it back as one string.
 *
 * The artifacts endpoint reports the build log with a null download_url —
 * it is read through /runs/{id}/logs rather than served as a file — so the
 * only way to offer it as a download is to page it and rejoin it here. Each
 * line's `message` is the raw log line verbatim, so joining on newline
 * reproduces the file. Paging is cursor-based, not offset, so fetchAll
 * cannot be reused.
 */
export async function fetchRunLog(runId: number, maxLines = 200_000): Promise<string> {
  const lines: string[] = [];
  let cursor: string | null = null;
  for (;;) {
    const after = cursor ? `&cursor=${encodeURIComponent(cursor)}` : "";
    const qs = `limit=500${after}`;
    const page: { data: { message: string }[]; pagination?: { next_cursor: string | null } } =
      await apiGet(`/runs/${runId}/logs?${qs}`);
    for (const l of page.data) lines.push(l.message);
    cursor = page.pagination?.next_cursor ?? null;
    if (cursor === null || page.data.length === 0 || lines.length >= maxLines) break;
  }
  return lines.join("\n");
}

/** Infra fault derived from progress messages (VM died, build never came). */
export interface InfraError {
  type: string;
  severity: string;
  message: string;
  timestamp?: string | null;
}

export function useInfraErrors(runId: number | null) {
  return useQuery({
    queryKey: ["run-infra-errors", runId],
    enabled: runId !== null,
    staleTime: 300_000,
    queryFn: () => fetchAll<InfraError>(`/runs/${runId}/infrastructure-errors`, 50),
  });
}

/** Unified diff for one failing output of a run. */
export async function fetchDiff(args: {
  runId: number;
  sampleId: number;
  regressionId: number;
  outputId: number;
}): Promise<{ content: string }> {
  return apiGet<{ content: string }>(
    `/runs/${args.runId}/samples/${args.sampleId}/regression-tests/${args.regressionId}` +
      `/outputs/${args.outputId}/diff?format=unified`,
  );
}

/**
 * One side of a failing comparison as text.
 *
 * The API reads the file itself rather than handing back a storage link, so
 * this needs no CORS grant on the bucket and works the same whether the copy
 * lives locally or in GCS. Anything past 1 MiB comes back truncated.
 */
export const outputText = (
  args: { runId: number; sampleId: number; regressionId: number; outputId: number },
  which: "expected" | "actual",
) =>
  apiGet<{ filename: string; content: string; truncated: boolean }>(
    `/runs/${args.runId}/samples/${args.sampleId}/regression-tests/${args.regressionId}` +
      `/outputs/${args.outputId}/${which}?format=text`,
  );

/** Category list derived from the live test suite. */
export function deriveCategories(tests: RegressionTest[]) {
  const counts = new Map<string, number>();
  for (const t of tests) for (const c of t.categories) counts.set(c, (counts.get(c) ?? 0) + 1);
  return [...counts.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([name, test_count], i) => ({ id: i + 1, name, description: "", test_count }));
}

/* ---------------- derived from the live suite ---------------- */

export function healthOf(t: RegressionTest): SparkResult {
  for (let i = t.recent_results.length - 1; i >= 0; i--) {
    if (t.recent_results[i] !== "skip") return t.recent_results[i];
  }
  return "skip";
}

export function categoryHealth(name: string, tests: RegressionTest[]) {
  const inCat = tests.filter((t) => t.categories.includes(name));
  return {
    total: inCat.length,
    failing: inCat.filter((t) => healthOf(t) === "fail").length,
  };
}

export function commandPresets(tests: RegressionTest[], limit = 6) {
  const counts = new Map<string, number>();
  for (const t of tests) counts.set(t.command, (counts.get(t.command) ?? 0) + 1);
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([command, count]) => ({ command, count }));
}

/* ---------------- uploads and the queue ---------------- */

export interface QueuedSample {
  id: number;
  sha: string;
  extension: string;
  original_name: string;
  user_id: number;
}

/**
 * Send a file to the upload queue.
 *
 * Multipart, so this cannot go through apiSend: that sets a JSON content
 * type, and the boundary has to be the one fetch generates for the
 * FormData.
 */
export async function uploadSample(file: File): Promise<QueuedSample> {
  const session = getSession();
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/samples/upload`, {
    method: "POST",
    headers: session ? { Authorization: `Bearer ${session.token}` } : {},
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw apiError(res.status, data.message ?? res.statusText);
  return data as QueuedSample;
}

export function useQueuedSamples() {
  return useQuery({
    queryKey: ["queued-samples"],
    staleTime: 15_000,
    queryFn: () => fetchAll<QueuedSample>("/queued-samples"),
  });
}

export const finalizeUpload = (
  id: number,
  body: { version: string; platform: Platform; parameters?: string; notes?: string },
) => apiSend<{ sample_id: number }>("POST", `/queued-samples/${id}/finalize`, body);

export const linkUpload = (id: number, sampleId: number) =>
  apiSend<{ id: number; sample_id: number }>("POST", `/queued-samples/${id}/link`, {
    sample_id: sampleId,
  });

export const discardUpload = (id: number) =>
  apiDelete<{ id: number; deleted: boolean }>(`/queued-samples/${id}`);

export interface FtpCredentials {
  host: string;
  port: string;
  username: string;
  password: string;
}

export function useFtpCredentials(enabled: boolean) {
  return useQuery({
    queryKey: ["ftp-credentials"],
    enabled,
    staleTime: Infinity,
    queryFn: () => apiGet<FtpCredentials>("/auth/me/ftp-credentials"),
  });
}

/* ---------------- tags and sample editing ---------------- */

export interface Tag {
  id: number;
  name: string;
  description: string;
}

export function useTags() {
  return useQuery({
    queryKey: ["tags"],
    staleTime: 300_000,
    queryFn: () => fetchAll<Tag>("/tags"),
  });
}

export const createTag = (name: string, description = "") =>
  apiSend<Tag>("POST", "/tags", { name, description });

export const updateSample = (
  id: number,
  patch: { tags?: string[]; notes?: string; parameters?: string; platform?: string; version?: string },
) => apiSend<{ sample_id: number; tags: string[] }>("PATCH", `/samples/${id}`, patch);

export const deleteSample = (id: number) =>
  apiDelete<{ sample_id: number; deleted: boolean }>(`/samples/${id}`);

export const mediaInfoFile = (sampleId: number) =>
  apiGet<StoredFile>(`/samples/${sampleId}/media-info/download`);

export const extraFile = (sampleId: number, extraId: number) =>
  apiGet<StoredFile>(`/samples/${sampleId}/extra-files/${extraId}/download`);

export const deleteExtraFile = (sampleId: number, extraId: number) =>
  apiDelete<{ id: number; deleted: boolean }>(
    `/samples/${sampleId}/extra-files/${extraId}`,
  );

/* ---------------- baseline variants ---------------- */

export const createVariant = (testId: number, outputId: number, hash: string) =>
  apiSend<{ id: number; hash: string }>(
    "POST", `/regression-tests/${testId}/outputs/${outputId}/variants`, { hash },
  );

export const deleteVariant = (testId: number, outputId: number, variantId: number) =>
  apiDelete<{ id: number; deleted: boolean }>(
    `/regression-tests/${testId}/outputs/${outputId}/variants/${variantId}`,
  );

/* ---------------- account ---------------- */

export interface Me {
  user_id: number;
  name: string;
  email: string;
  role: PlatformUser["role"];
  scopes: string[];
}

/**
 * The account behind the current token.
 *
 * The stored session only keeps the email that was typed at sign-in, so
 * anything that edits the account has to read the server's copy instead.
 */
export function useMe() {
  return useQuery({
    queryKey: ["me"],
    staleTime: 300_000,
    queryFn: () => apiGet<Me>("/auth/me"),
  });
}

export const requestSignup = (email: string) =>
  apiSend<{ sent: boolean }>("POST", "/auth/signup", { email });

export const requestPasswordReset = (email: string) =>
  apiSend<{ sent: boolean }>("POST", "/auth/password-reset", { email });

/** Finish a reset from the link in the email. Nobody is signed in here. */
export const completePasswordReset = (body: {
  user_id: number;
  expires: number;
  mac: string;
  password: string;
}) =>
  apiSend<{ user_id: number; password_changed: boolean }>(
    "POST", "/auth/password-reset/complete", body,
  );

export interface GithubLink {
  linked: boolean;
  github_login: string | null;
  authorize_url: string;
}

export function useGithubLink() {
  return useQuery({
    queryKey: ["github-link"],
    staleTime: 60_000,
    queryFn: () => apiGet<GithubLink>("/auth/me/github"),
  });
}

export const unlinkGithub = () =>
  apiDelete<{ linked: boolean }>("/auth/me/github");

export const updateAccount = (patch: {
  name?: string;
  email?: string;
  new_password?: string;
  current_password?: string;
}) => apiSend<PlatformUser>("PATCH", "/auth/me", patch);

export const sendUserReset = (userId: number) =>
  apiSend<{ sent: boolean }>("POST", `/users/${userId}/password-reset`, {});

export const deactivateUser = (userId: number) =>
  apiSend<{ deactivated: boolean }>("POST", `/users/${userId}/deactivate`, {});

/* ---------------- platform ---------------- */

export interface About {
  platform_commit: string | null;
  ccextractor_version: string | null;
  ccextractor_released: string | null;
  last_tested_commit: string | null;
}

export function useAbout() {
  return useQuery({
    queryKey: ["about"],
    staleTime: 600_000,
    queryFn: () => apiGet<About>("/system/about"),
  });
}

export const restartRun = (runId: number) =>
  apiSend<{ status: string; message: string }>("POST", `/runs/${runId}/restart`, {});
