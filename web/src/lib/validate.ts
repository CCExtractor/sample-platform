// Input validation for values that end up on CI infrastructure or inside
// rendered links. The server is the real gate — these exist so obviously bad
// input fails fast in the form, and so a hostile API response can't smuggle
// a javascript: URL into an <a href>.

/** Full 40-hex commit SHA. */
export const isCommitSha = (v: string) => /^[a-fA-F0-9]{40}$/.test(v);

/** GitHub "owner/repo" slug. */
export const isRepoSlug = (v: string) => /^[\w.-]+\/[\w.-]+$/.test(v);

/**
 * Git allows almost anything in a ref name, but nothing we forward to CI
 * needs whitespace, shell metacharacters or a leading dash. Rejecting them
 * here beats trusting every downstream consumer to quote properly.
 */
export const isBranchName = (v: string) => /^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$/.test(v);

/** Length cap for regression-test commands (they execute on CI VMs). */
export const COMMAND_MAX = 512;

/**
 * Allowlist for outbound links. React does not sanitize href schemes, so an
 * API-supplied javascript: URL would execute in our origin on click. Only
 * github.com URLs ever come back from the platform, so only those render
 * as links; anything else is dropped.
 */
export function githubUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  return /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+([/?#]|$)/.test(url) ? url : null;
}

/**
 * Allowlist for artifact download links. Same reasoning as githubUrl — these
 * come straight from the API (signed storage URLs), and a javascript:/data:
 * value would run in our origin on click. Only https:// downloads are ever
 * expected; anything else renders as no link.
 */
export function httpsUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  return /^https:\/\//i.test(url) ? url : null;
}
