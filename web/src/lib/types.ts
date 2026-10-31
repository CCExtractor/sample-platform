// Domain types. Field names follow the API's serializers so responses can
// be used mostly as-is; the snapshot JSON under src/mocks/generated uses
// the same shapes.

export type Platform = "linux" | "windows";

/** Normalized run statuses from mod_api services/status.py, plus the VM
 * progress phases reported while a run executes. */
export type RunStatus =
  | "queued"
  | "running"
  | "pass"
  | "fail"
  | "canceled"
  | "error"
  | "incomplete"
  | "preparation"
  | "building"
  | "testing"
  | "completed";

export type SparkResult = "pass" | "fail" | "skip";

export interface Category {
  id: number;
  name: string;
  description: string;
  test_count: number;
}

export interface RegressionTest {
  id: number;
  sample_id: number;
  sample_name: string;
  sample_sha: string;
  command: string;
  input_type: string | null;
  output_type: string | null;
  expected_rc: number;
  active: boolean;
  description: string;
  categories: string[];
  avg_runtime_ms: number | null;
  /** Recent runs, oldest first. Baselines come from the detail endpoint. */
  recent_results: SparkResult[];
}

export interface Sample {
  id: number;
  sha: string;
  extension: string;
  original_name: string;
  tags: string[];
  test_count: number;
}

/** Raw run row from GET /api/v1/runs. */
export interface LiveRun {
  run_id: number;
  status: RunStatus;
  platform: Platform;
  test_type: "pr" | "commit";
  repository: string;
  branch: string;
  commit_sha: string;
  pr_number: number | null;
  created_at: string | null;
  queued_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  github_link: string | null;
}

/** GET /api/v1/runs/<id>/summary */
export interface RunSummary {
  run_id: number;
  status: RunStatus;
  total_samples: number;
  pass_count: number;
  fail_count: number;
  error_count: number;
  missing_output_count: number;
  skipped_count: number;
  duration_ms: number | null;
}

export interface LogicalPlatformRun {
  run_id: number;
  platform: Platform;
  status: RunStatus;
  started_at: string | null;
  completed_at: string | null;
}

/** Logical run = all platforms for one commit/PR event (grouped client-side). */
export interface LogicalRun {
  id: string;
  commit: string;
  branch: string;
  fork: string;
  pr_nr: number | null;
  test_type: "pr" | "commit";
  created_at: string | null;
  github_link: string | null;
  platforms: LogicalPlatformRun[];
}

/** Snapshot run shape (mocks/generated/runs.json, from prod dump). */
export interface SnapshotPlatformRun {
  test_id: number;
  platform: Platform;
  status: string;
  message: string;
  passed: number;
  failed: number;
  new_failures: number;
  total: number;
  duration_s: number | null;
  started_at: string | null;
  failing_ids: number[];
}


