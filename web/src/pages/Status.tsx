import { Link } from "@tanstack/react-router";
import { Activity, CircleCheck, CircleSlash, TriangleAlert } from "lucide-react";
import { useMemo } from "react";

import { RunStatusBadge } from "@/components/StatusBadge";
import { useHealth, useQueue, useRuns } from "@/lib/api";
import type { Platform, RunStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Platform status at a glance — health, CI queue depth, and the last master
 * run per platform. Replaces "is the platform down? better ask on IRC" with a
 * single page. Composes read-only endpoints only, so it works the moment the
 * API is reachable.
 */
const PLATFORMS: Platform[] = ["linux", "windows"];

/** The three states the platform banner can be in. */
function HealthIcon({ ok, degraded }: Readonly<{ ok: boolean; degraded: boolean }>) {
  if (ok) return <CircleCheck className="size-6 text-success" />;
  if (degraded) return <TriangleAlert className="size-6 text-warning" />;
  return <CircleSlash className="size-6 text-destructive" />;
}

function headline(loaded: boolean, ok: boolean, degraded: boolean): string {
  if (!loaded) return "Checking…";
  if (ok) return "All systems operational";
  return degraded ? "Degraded — some dependencies are unhealthy" : "Platform is down";
}

function dependencyDot(status: string): string {
  if (status === "ok") return "bg-success";
  return status === "degraded" ? "bg-warning" : "bg-destructive";
}

export function Status() {
  const { data: health } = useHealth();
  const { data: queue } = useQueue();
  const { data: runs = [] } = useRuns();

  // Most recent master run touching each platform.
  const lastMaster = useMemo(() => {
    const out: Record<Platform, { commit: string; status: RunStatus; at: string | null } | null> = {
      linux: null,
      windows: null,
    };
    for (const platform of PLATFORMS) {
      for (const run of runs) {
        if (run.test_type !== "commit" || run.branch !== "master") continue;
        const p = run.platforms.find((x) => x.platform === platform);
        if (p) {
          out[platform] = { commit: run.commit, status: p.status, at: p.completed_at ?? p.started_at };
          break; // runs are newest-first
        }
      }
    }
    return out;
  }, [runs]);

  const ok = health?.status === "ok";
  const degraded = health?.status === "degraded";

  return (
    <div>
      <div className="sticky top-0 z-10 border-b bg-card/85 px-6 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <h1 className="text-[15px] font-semibold tracking-tight">Platform status</h1>
          <span className="text-xs text-faint">health, queue and last run on master</span>
        </div>
      </div>

      <div className="mx-auto flex max-w-3xl flex-col gap-5 px-6 py-6">
        {/* Headline banner */}
        <div
          className={cn(
            "flex items-center gap-3 rounded-xl border p-4",
            !health && "bg-muted/40",
            ok && "border-success/30 bg-success/10",
            degraded && "border-warning/40 bg-warning/10",
            health && !ok && !degraded && "border-destructive/40 bg-destructive/10",
          )}
        >
          <HealthIcon ok={ok} degraded={degraded} />
          <div>
            <div className="text-[14px] font-semibold">
              {headline(!!health, ok, degraded)}
            </div>
            <div className="text-[12px] text-faint">
              {health
                ? `${health.dependencies.filter((d) => d.status === "ok").length}/${health.dependencies.length} dependencies healthy`
                : "Contacting the API…"}
            </div>
          </div>
        </div>

        {/* Dependencies */}
        {health && (
          <div className="flex flex-wrap gap-2">
            {health.dependencies.map((d) => (
              <span
                key={d.name}
                className="inline-flex items-center gap-1.5 rounded-lg border bg-card px-2.5 py-1 text-[12px] shadow-card"
              >
                <span
                  className={cn(
                    "size-2 rounded-full",
                    dependencyDot(d.status),
                  )}
                />
                <span className="font-medium">{d.name}</span>
                <span className="text-faint">{d.status}</span>
              </span>
            ))}
          </div>
        )}

        <div className="grid gap-4 md:grid-cols-2">
          {/* Queue */}
          <section className="rounded-xl border bg-card p-4 shadow-card">
            <div className="mb-3 flex items-center gap-2 text-[13px] font-semibold">
              <Activity className="size-4 text-primary" /> CI queue
              {queue && (
                <span className="ml-auto text-[11px] font-normal text-faint">
                  {queue.meta.running_count} running · {queue.meta.queue_depth} queued
                </span>
              )}
            </div>
            <div className="flex flex-col gap-1">
              {(queue?.data ?? []).map((j) => (
                <div key={j.run_id} className="flex items-center gap-2 text-[12px]">
                  <code className="text-faint">run {j.run_id}</code>
                  <span className="uppercase tracking-wider text-muted-foreground">{j.platform}</span>
                  <RunStatusBadge status={j.status as RunStatus} className="ml-auto" />
                </div>
              ))}
              {queue?.data.length === 0 && (
                <div className="py-4 text-center text-[12px] text-faint">Queue is empty.</div>
              )}
            </div>
          </section>

          {/* Last master run per platform */}
          <section className="rounded-xl border bg-card p-4 shadow-card">
            <div className="mb-3 text-[13px] font-semibold">Last master run</div>
            <div className="flex flex-col gap-2">
              {PLATFORMS.map((platform) => {
                const last = lastMaster[platform];
                return (
                  <div key={platform} className="flex items-center gap-2 text-[12px]">
                    <span className="w-14 shrink-0 uppercase tracking-wider text-muted-foreground">
                      {platform}
                    </span>
                    {last ? (
                      <>
                        <code className="text-faint">{last.commit}</code>
                        <RunStatusBadge status={last.status} className="ml-auto" />
                      </>
                    ) : (
                      <span className="ml-auto text-faint">no recent run</span>
                    )}
                  </div>
                );
              })}
            </div>
            <Link
              to="/runs"
              className="mt-3 inline-block text-[11px] text-primary hover:underline"
            >
              All test results →
            </Link>
          </section>
        </div>
      </div>
    </div>
  );
}
