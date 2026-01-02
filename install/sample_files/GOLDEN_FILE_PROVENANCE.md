# Golden File Provenance

This document tracks the generation details for regression test golden files.

## sample1.webvtt

| Field | Value |
|-------|-------|
| Generated | 2026-01-02 |
| CCExtractor Version | 0.96.3 |
| Binary | ccextractorwinfull.exe |
| Platform | Windows x64 |
| Source Commit | Release build from windows/x64/Release-Full |
| Command | `ccextractorwinfull.exe sample1.ts -out=webvtt -o sample1.webvtt` |
| Input Sample | sample1.ts (no embedded closed captions) |
| Expected Output | WebVTT header only (WEBVTT + blank line) |

### Reproduction Steps

```bash
ccextractor install/sample_files/sample1.ts -out=webvtt -o install/sample_files/sample1.webvtt
```

### Notes

- sample1.ts contains no closed caption data, so output is header-only
- This test validates WebVTT header generation, not full cue formatting
- For full WebVTT validation, a sample with embedded captions should be added
