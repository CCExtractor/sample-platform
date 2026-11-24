/**
 * Word-level highlighting for the diff drawer.
 *
 * The API returns a line-level unified diff. For caption files the changed
 * line usually differs by one space or a few milliseconds, which a whole red
 * line next to a whole green line hides. Pairing each removed line with the
 * added line that replaced it and marking only the tokens that differ is what
 * makes those visible.
 */

export interface Seg {
  text: string;
  changed: boolean;
  /** Offset of the segment in its line: unique per line, so a stable key. */
  at: number;
}

export interface DiffRow {
  /** Position in the rendered diff, assigned once here as the row's key. */
  id: number;
  kind: "ctx" | "del" | "add" | "hunk";
  segs: Seg[];
}

// Runs of letters/digits, runs of whitespace, and single punctuation marks:
// "03,520" splits into 03 , 520 so a timing change marks only the digits.
const TOKEN = /\s+|\w+|[^\w\s]/g;

// Beyond this many token pairs a line is not a caption line; mark it whole.
const MAX_CELLS = 250_000;

function push(out: Seg[], text: string, changed: boolean) {
  const last = out.at(-1);
  if (last?.changed === changed) last.text += text;
  else out.push({ text, changed, at: last ? last.at + last.text.length : 0 });
}

/** A whole line as one segment. */
export const whole = (text: string, changed = false): Seg[] => [{ text, changed, at: 0 }];

/** Split two lines into segments, marking the tokens not in their LCS. */
export function wordDiff(a: string, b: string): [Seg[], Seg[]] {
  const x = a.match(TOKEN) ?? [];
  const y = b.match(TOKEN) ?? [];
  const n = x.length;
  const m = y.length;
  if (n * m > MAX_CELLS) {
    return [whole(a, true), whole(b, true)];
  }

  // L[i][j] = LCS length of x[i..] and y[j..]. Values never exceed
  // min(n, m) <= 500 under MAX_CELLS, so 16 bits is plenty.
  const L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
    }
  }

  const left: Seg[] = [];
  const right: Seg[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (x[i] === y[j]) {
      push(left, x[i++], false);
      push(right, y[j++], false);
    } else if (L[i + 1][j] >= L[i][j + 1]) {
      push(left, x[i++], true);
    } else {
      push(right, y[j++], true);
    }
  }
  while (i < n) push(left, x[i++], true);
  while (j < m) push(right, y[j++], true);
  return [left, right];
}

/**
 * Unified diff text to display rows. Within a hunk, each run of removed lines
 * is paired in order with the run of added lines after it, and the pairs are
 * interleaved (-a +a -b +b) so each old line sits directly above its new one.
 */
export function diffRows(unified: string): DiffRow[] {
  const rows: DiffRow[] = [];
  let del: string[] = [];
  let add: string[] = [];
  const row = (kind: DiffRow["kind"], segs: Seg[]) => rows.push({ id: rows.length, kind, segs });

  const flush = () => {
    for (let k = 0; k < Math.max(del.length, add.length); k++) {
      const a = del[k];
      const b = add[k];
      if (a !== undefined && b !== undefined) {
        const [l, r] = wordDiff(a, b);
        row("del", l);
        row("add", r);
      } else if (a !== undefined) {
        row("del", whole(a));
      } else {
        row("add", whole(b));
      }
    }
    del = [];
    add = [];
  };

  unified.split("\n").forEach((line, idx) => {
    // The "--- expected" / "+++ actual" file header is always the first two
    // lines; anything later starting with "---" is a removed "--" line.
    if (idx < 2 && /^(---|\+\+\+) /.test(line)) return;
    if (line.startsWith("-")) {
      if (add.length) flush();
      del.push(line.slice(1));
    } else if (line.startsWith("+")) {
      add.push(line.slice(1));
    } else {
      flush();
      const hunk = line.startsWith("@@");
      row(hunk ? "hunk" : "ctx", whole(hunk ? line : line.replace(/^ /, "")));
    }
  });
  flush();
  return rows;
}
