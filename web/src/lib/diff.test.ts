import { describe, expect, it } from "vitest";

import { diffRows, wordDiff, type Seg } from "@/lib/diff";

const changed = (segs: Seg[]) => segs.filter((s) => s.changed).map((s) => s.text);

describe("wordDiff", () => {
  it("marks only the digits of a one-frame timing shift", () => {
    const [l, r] = wordDiff(
      "00:00:01,480|00:00:03,520|TLT|hi",
      "00:00:01,480|00:00:03,560|TLT|hi",
    );
    expect(changed(l)).toEqual(["520"]);
    expect(changed(r)).toEqual(["560"]);
  });

  it("marks an inserted space on the side that has it", () => {
    const [l, r] = wordDiff("My,um...", "My, um...");
    expect(changed(l)).toEqual([]);
    expect(changed(r)).toEqual([" "]);
  });
});

describe("diffRows", () => {
  it("interleaves removed and added lines, drops the header, keeps a -- line", () => {
    const rows = diffRows(
      ["--- expected", "+++ actual", "@@ -1,3 +1,3 @@", " same", "-a 1", "-b 1", "--- x", "+a 2", "+b 2"].join(
        "\n",
      ),
    );
    expect(rows.map((x) => x.kind)).toEqual(["hunk", "ctx", "del", "add", "del", "add", "del"]);
    expect(rows[6].segs[0].text).toBe("-- x");
  });
});
