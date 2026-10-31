import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * URL for a file in public/, honouring the base the bundle was built with.
 *
 * The console is served from /app/ on the platform's domain rather than from
 * a root, and Vite only rewrites paths it can see — those in index.html, not
 * string literals inside components.
 */
export function asset(name: string): string {
  return `${import.meta.env.BASE_URL}${name}`;
}
