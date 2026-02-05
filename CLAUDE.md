# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CCExtractor Sample Platform - Flask web application for managing regression tests, sample uploads, and CI/CD for the CCExtractor project. Validates PRs by running CCExtractor against sample media files on GCP VMs (Linux/Windows).

## Tech Stack

- **Backend**: Flask 3.1, SQLAlchemy 1.4, MySQL (SQLite for tests)
- **Cloud**: GCP Compute Engine (test VMs), Google Cloud Storage (samples)
- **CI/CD**: GitHub Actions, GitHub API (PyGithub)
- **Testing**: nose2, Flask-Testing, coverage

## Commands

```bash
# Setup
virtualenv venv && source venv/bin/activate
pip install -r requirements.txt
pip install -r test-requirements.txt

# Run tests
TESTING=True nose2

# Linting & type checking
pycodestyle ./ --config=./.pycodestylerc
pydocstyle ./
mypy .
isort . --check-only

# Database migrations
export FLASK_APP=/path/to/run.py
flask db upgrade      # Apply migrations
flask db migrate      # Generate new migration

# Update regression test results
python manage.py update /path/to/ccextractor
```

## Architecture

### Module Structure
Each module in `mod_*/` follows: `__init__.py`, `controllers.py` (routes), `models.py` (ORM), `forms.py` (WTForms)

| Module | Purpose |
|--------|---------|
| `mod_ci` | GitHub webhooks, GCP VM orchestration, test execution |
| `mod_regression` | Regression test definitions, categories, expected outputs |
| `mod_test` | Test runs, results, progress tracking |
| `mod_sample` | Sample file management, tags, extra files |
| `mod_upload` | HTTP/FTP upload handling |
| `mod_auth` | User auth, roles (admin/user/contributor/tester) |
| `mod_customized` | Custom test runs for forks |

### Key Models & Relationships
```
Sample (sha hash) -> RegressionTest (command, expected_rc) -> RegressionTestOutput
                                    |
Fork (GitHub repo) -> Test (platform, commit) -> TestResult -> TestResultFile
                                              -> TestProgress (status tracking)
```

### CI Flow
1. GitHub webhook (`/start-ci`) receives PR/push events
2. Waits for GitHub Actions build artifacts
3. `gcp_instance()` provisions Linux/Windows VMs
4. VMs run CCExtractor, report to `progress_reporter()`
5. Results compared against expected outputs
6. `comment_pr()` posts results to GitHub

## Critical Files

- `run.py` - Flask app entry, blueprint registration
- `mod_ci/controllers.py` - CI orchestration (2500+ lines)
- `mod_regression/models.py` - Test definitions
- `mod_test/models.py` - Test execution models
- `database.py` - SQLAlchemy setup, custom types
- `tests/base.py` - Test fixtures, mock helpers

## GSoC 2026 Focus Areas (from Carlos)

### Priority 1: Regression Test Suite
The main blocker for CCExtractor Rust migration is test coverage. Current needs:
- Add regression tests for uncovered caption types/containers
- Import FFmpeg and VLC official video libraries as test samples
- Systematic sample analysis using ffprobe, mkvnix, CCExtractor output
- Goal: Trust SP enough that passing tests = safe to merge

### Priority 2: Sample Platform Improvements
Low-coverage modules needing work:
- `mod_upload` (44% coverage) - FTP upload, progress tracking
- `mod_test` (58% coverage) - diff generation, error scenarios
- `mod_sample` (61% coverage) - Issue linking, tag management

### Contribution Strategy
1. Start with unit tests for low-coverage modules
2. Add integration tests for CI flow
3. Help document sample metadata systematically
4. Enable confident C code removal by proving test coverage

## Code Style

- Type hints required (mypy enforced)
- Docstrings required (pydocstyle enforced)
- PEP8 (pycodestyle enforced)
- Imports sorted with isort

## MCP Setup (GSoC 2026)

**Configured servers** (`~/.claude/settings.json`):
- `github` – repo/PR/issue management (needs `GITHUB_PERSONAL_ACCESS_TOKEN` env var)
- `context7` – up-to-date library docs
- `filesystem` – scoped to `/home/rahul/projects/gsoc`

**Security**:
- Token stored in `~/.profile`, never committed
- MCP paths added to `.gitignore`
- pm2 config at `~/ecosystem.config.js` for auto-restart

**Commands**:
```bash
# Start MCP servers
pm2 start ~/ecosystem.config.js
pm2 logs

# Resume Claude session
claude --resume
```
