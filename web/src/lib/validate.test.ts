import { describe, expect, it } from "vitest";

import {
  githubUrl,
  httpsUrl,
  isBranchName,
  isCommitSha,
  isRepoSlug,
} from "@/lib/validate";

describe("githubUrl", () => {
  it("keeps a real github.com https URL", () => {
    expect(githubUrl("https://github.com/CCExtractor/ccextractor")).toBe(
      "https://github.com/CCExtractor/ccextractor",
    );
  });

  it("drops javascript: and non-github hrefs so they never reach <a>", () => {
    expect(githubUrl("javascript:alert(1)")).toBeNull();
    expect(githubUrl("https://evil.example/CCExtractor/ccextractor")).toBeNull();
    expect(githubUrl("http://github.com/CCExtractor/ccextractor")).toBeNull();
    expect(githubUrl(null)).toBeNull();
  });
});

describe("httpsUrl", () => {
  it("allows signed https downloads and rejects data/javascript", () => {
    expect(httpsUrl("https://storage.googleapis.com/bucket/file")).toBe(
      "https://storage.googleapis.com/bucket/file",
    );
    expect(httpsUrl("javascript:alert(1)")).toBeNull();
    expect(httpsUrl("data:text/html,hi")).toBeNull();
  });
});

describe("form gates", () => {
  it("accepts a full 40-hex SHA and a owner/repo slug", () => {
    expect(isCommitSha("a".repeat(40))).toBe(true);
    expect(isCommitSha("a".repeat(39))).toBe(false);
    expect(isRepoSlug("CCExtractor/sample-platform")).toBe(true);
    expect(isRepoSlug("not-a-slug")).toBe(false);
  });

  it("rejects branch names that would be unsafe to forward to CI", () => {
    expect(isBranchName("fix/restart-clears-gcp")).toBe(true);
    expect(isBranchName("-leading-dash")).toBe(false);
    expect(isBranchName("has space")).toBe(false);
    expect(isBranchName("bad;rm -rf")).toBe(false);
  });
});
