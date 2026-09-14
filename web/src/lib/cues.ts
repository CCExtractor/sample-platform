/**
 * Timestamped lines pulled out of a caption file.
 *
 * CCExtractor writes SubRip and WebVTT with the same timing shape, differing
 * only in the decimal separator, so one expression covers both. Formats with
 * no timings at all — the plain .txt transcripts — yield nothing, and the
 * caller falls back to showing the file as it is.
 */
export interface Cue {
  start: number;
  end: number;
  text: string;
}

const TIMING =
  /(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})/;

const seconds = (h: string, m: string, s: string, ms: string) =>
  +h * 3600 + +m * 60 + +s + +ms / 1000;

export function parseCues(source: string): Cue[] {
  const cues: Cue[] = [];
  for (const block of source.replaceAll("\r", "").split(/\n{2,}/)) {
    const lines = block.split("\n");
    // The timing line is the anchor: what precedes it is a cue number or a
    // WEBVTT header, and what follows is the caption itself.
    const at = lines.findIndex((l) => TIMING.test(l));
    if (at === -1) continue;
    const m = TIMING.exec(lines[at])!;
    const text = lines.slice(at + 1).join("\n").trim();
    if (text === "") continue;
    cues.push({
      start: seconds(m[1], m[2], m[3], m[4]),
      end: seconds(m[5], m[6], m[7], m[8]),
      text,
    });
  }
  return cues;
}

/** mm:ss for the cue gutter — samples are minutes long, never hours. */
export function clock(t: number): string {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Render cues back as a WebVTT file, for a <track> on the player. */
export function cuesToVtt(cues: Cue[]): string {
  const stamp = (t: number) => {
    const h = Math.floor(t / 3600);
    const m = Math.floor((t % 3600) / 60);
    const s = Math.floor(t % 60);
    const ms = Math.round((t % 1) * 1000);
    const pad = (n: number, w = 2) => String(n).padStart(w, "0");
    return `${pad(h)}:${pad(m)}:${pad(s)}.${pad(ms, 3)}`;
  };
  const body = cues
    .map((c) => `${stamp(c.start)} --> ${stamp(c.end)}\n${c.text}`)
    .join("\n\n");
  return `WEBVTT\n\n${body}`;
}
