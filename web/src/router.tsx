import {
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router";

import { AppShell } from "@/components/layout/AppShell";
import { ResetPassword } from "@/components/ResetPassword";
import { Account } from "@/pages/Account";
import { Admin } from "@/pages/Admin";
import { RunDetail } from "@/pages/RunDetail";
import { RunNew } from "@/pages/RunNew";
import { Runs } from "@/pages/Runs";
import { Samples } from "@/pages/Samples";
import { Status } from "@/pages/Status";
import { TestBuilder } from "@/pages/TestBuilder";
import { Triage } from "@/pages/Triage";
import { Upload } from "@/pages/Upload";
import { Workspace } from "@/pages/Workspace";
import { canManage, getSession } from "@/lib/auth";

const rootRoute = createRootRoute({ component: AppShell });

const homeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: Triage,
});

const runsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/runs",
  component: Runs,
});

const runNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/runs/new",
  component: RunNew,
  // ?test=<id> scopes the run to a single regression test (the builder's
  // "queue verification run" entry point).
  validateSearch: (search: Record<string, unknown>): { test?: number } => ({
    test: search.test ? Number(search.test) : undefined,
  }),
});

const runDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/runs/$runId",
  component: RunDetail,
});

const testsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tests",
  component: Workspace,
  validateSearch: (search: Record<string, unknown>): { t?: number } => ({
    t: search.t ? Number(search.t) : undefined,
  }),
});

function AdminOnly({ children }: Readonly<{ children: React.ReactNode }>) {
  if (!canManage(getSession())) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
        <h1 className="text-[15px] font-semibold">Administrators only</h1>
        <p className="max-w-md text-[13px] text-faint">
          Creating or removing regression tests is restricted to admins and contributors.
        </p>
      </div>
    );
  }
  return <>{children}</>;
}

const testBuilderRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tests/new",
  component: () => (
    <AdminOnly>
      <TestBuilder />
    </AdminOnly>
  ),
});

const samplesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/samples",
  component: Samples,
});

const uploadRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/upload",
  component: Upload,
});

const statusRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/status",
  component: Status,
});

// Reached from a recovery email, so it must render with no session. The
// shell hands this path straight through.
const resetRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/reset",
  component: ResetPassword,
});

const accountRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/account",
  component: Account,
});

const adminRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin",
  component: () => (
    <AdminOnly>
      <Admin />
    </AdminOnly>
  ),
});

const routeTree = rootRoute.addChildren([
  homeRoute,
  runsRoute,
  runNewRoute,
  runDetailRoute,
  testsRoute,
  testBuilderRoute,
  uploadRoute,
  samplesRoute,
  statusRoute,
  resetRoute,
  accountRoute,
  adminRoute,
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
