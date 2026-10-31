import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import {
  Activity,
  FileVideo,
  FlaskConical,
  Gauge,
  Inbox,
  LogOut,
  Moon,
  Search,
  Settings,
  Sun,
  UploadCloud,
} from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState } from "react";

import { CommandPalette } from "@/components/CommandPalette";
import { Login } from "@/components/Login";
import { SESSION_CHANGED, getSession, logout } from "@/lib/auth";
import { asset, cn } from "@/lib/utils";

/* Classic-site menu names so migrating devs feel at home. */
const sections = [
  {
    id: "main",
    label: null,
    items: [
      { to: "/", label: "Home", icon: Inbox },
      { to: "/runs", label: "Test results", icon: Activity },
    ],
  },
  {
    id: "suite",
    label: "Suite",
    items: [
      { to: "/tests", label: "Regression tests", icon: FlaskConical },
      { to: "/samples", label: "Samples", icon: FileVideo },
      { to: "/upload", label: "Sample upload", icon: UploadCloud },
    ],
  },
  {
    id: "platform",
    label: "Platform",
    items: [
      { to: "/status", label: "Platform status", icon: Gauge },
      { to: "/admin", label: "Administration", icon: Settings },
    ],
  },
] as const;

function useTheme() {
  const [dark, setDark] = useState(() => localStorage.getItem("sp-theme") === "dark");
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("sp-theme", dark ? "dark" : "light");
  }, [dark]);
  return { dark, toggle: () => setDark((d) => !d) };
}

const COLLAPSED = 52;
const EXPANDED = 224;

export function AppShell() {
  const { dark, toggle } = useTheme();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const [session, setSession] = useState(getSession);
  const [open, setOpen] = useState(false);

  // The account page can change the email shown here, so pick the stored
  // session back up instead of leaving the corner reading the old one.
  useEffect(() => {
    const sync = () => setSession(getSession());
    window.addEventListener(SESSION_CHANGED, sync);
    return () => window.removeEventListener(SESSION_CHANGED, sync);
  }, []);

  // The reset screen arrives from an email with nobody signed in, so it
  // renders on its own rather than behind the sign-in gate.
  if (pathname === "/reset") return <Outlet />;
  if (!session) return <Login onDone={() => setSession(getSession())} />;

  return (
    <div className="relative flex h-full overflow-hidden p-2">
      {/* Rail reserves collapsed width; sidebar overlays on hover so main never reflows. */}
      <div style={{ width: COLLAPSED }} className="shrink-0" />

      <motion.aside
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        initial={false}
        animate={{ width: open ? EXPANDED : COLLAPSED }}
        transition={{ type: "spring", stiffness: 420, damping: 38 }}
        className={cn(
          "absolute inset-y-2 left-2 z-30 flex flex-col overflow-hidden rounded-xl",
          open && "border bg-card shadow-pop",
        )}
      >
        <div className="flex items-center gap-2.5 px-2.5 py-2.5">
          <img src={asset("ccx.svg")} alt="CCExtractor" className="size-7 shrink-0" />
          <span
            className={cn(
              "whitespace-nowrap text-[13px] font-semibold tracking-tight transition-opacity",
              open ? "opacity-100" : "opacity-0",
            )}
          >
            Sample Platform
          </span>
          {open && (
            <button
              onClick={toggle}
              aria-label="Toggle theme"
              className="ml-auto cursor-pointer rounded-md p-1.5 text-faint transition-colors hover:bg-muted hover:text-foreground"
            >
              {dark ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}
            </button>
          )}
        </div>

        <div className="mb-2 px-1.5">
          {open ? (
            <CommandPalette />
          ) : (
            <div className="flex h-8 items-center rounded-lg px-2 text-faint">
              <Search className="size-4 shrink-0" />
            </div>
          )}
        </div>

        <nav className="flex flex-1 flex-col gap-3 overflow-y-auto overflow-x-hidden px-1.5">
          {sections.map((section) => (
            <div key={section.id} className="flex flex-col gap-px">
              {/* Always reserve the header row so icons don't shift on expand. */}
              <div className="h-4 px-2 pb-1 text-[11px] font-medium text-faint">
                <span className={cn("transition-opacity", open ? "opacity-100" : "opacity-0")}>
                  {section.label ?? ""}
                </span>
              </div>
              {section.items.map(({ to, label, icon: Icon }) => {
                const active = to === "/" ? pathname === "/" : pathname.startsWith(to);
                return (
                  <Link
                    key={to}
                    to={to}
                    title={label}
                    className={cn(
                      "relative flex h-8 items-center gap-2.5 rounded-md px-2 text-[13px] font-medium transition-colors",
                      active
                        ? "text-foreground"
                        : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
                    )}
                  >
                    {active && (
                      <motion.span
                        layoutId="nav-active"
                        className="absolute inset-0 rounded-md bg-muted shadow-card"
                        transition={{ type: "spring", stiffness: 500, damping: 40 }}
                      />
                    )}
                    <Icon className={cn("relative size-4 shrink-0", active ? "text-primary" : "text-faint")} />
                    <span
                      className={cn(
                        "relative whitespace-nowrap transition-opacity",
                        open ? "opacity-100" : "opacity-0",
                      )}
                    >
                      {label}
                    </span>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="flex items-center gap-2 px-2.5 py-2">
          {/* The whole identity block is the way to the account page — the
              classic site puts it behind the same name in the corner. */}
          <Link
            to="/account"
            title="Your account"
            className="flex min-w-0 flex-1 items-center gap-2 transition-opacity hover:opacity-75"
          >
            <div className="flex size-6 shrink-0 items-center justify-center rounded-full bg-accent text-[10px] font-semibold uppercase text-accent-foreground">
              {session.email.slice(0, 2)}
            </div>
            {open && (
              <div className="min-w-0 leading-tight">
                <div className="truncate text-xs font-medium">{session.email}</div>
                <div className="text-[10px] capitalize text-faint">{session.role}</div>
              </div>
            )}
          </Link>
          {open && (
            <button
              onClick={logout}
              title="Sign out"
              className="cursor-pointer rounded-md p-1.5 text-faint transition-colors hover:bg-muted hover:text-foreground"
            >
              <LogOut className="size-3.5" />
            </button>
          )}
        </div>
      </motion.aside>

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl border bg-card shadow-card">
        <motion.div
          key={pathname}
          className="min-h-0 flex-1 overflow-y-auto"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.22, ease: [0.25, 0.1, 0.25, 1] }}
        >
          <Outlet />
        </motion.div>
      </main>
    </div>
  );
}
