import { describe, expect, it } from "vitest";

import { clock, cuesToVtt, parseCues } from "@/lib/cues";

const SRT = `1
00:00:01,000 --> 00:00:02,500
Hello

2
00:00:03,000 --> 00:00:04,000
World
`;

const VTT = `WEBVTT

00:00:01.000 --> 00:00:02.500
Hello
`;

describe("parseCues", () => {
  it("reads SubRip commas and WebVTT dots as the same timings", () => {
    const srt = parseCues(SRT);
    const vtt = parseCues(VTT);
    expect(srt).toEqual([
      { start: 1, end: 2.5, text: "Hello" },
      { start: 3, end: 4, text: "World" },
    ]);
    expect(vtt).toEqual([{ start: 1, end: 2.5, text: "Hello" }]);
  });

  it("yields nothing for a plain transcript so the caller can show the file", () => {
    expect(parseCues("just some text\nno timings")).toEqual([]);
  });
});

describe("clock / cuesToVtt", () => {
  it("formats the cue gutter as m:ss", () => {
    expect(clock(0)).toBe("0:00");
    expect(clock(65)).toBe("1:05");
  });

  it("round-trips cues into a WebVTT track", () => {
    const vtt = cuesToVtt([{ start: 1, end: 2.5, text: "Hello" }]);
    expect(vtt.startsWith("WEBVTT\n\n")).toBe(true);
    expect(vtt).toContain("00:00:01.000 --> 00:00:02.500");
    expect(vtt).toContain("Hello");
  });
});
