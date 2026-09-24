# Commit Guide for Contextkit

## Quick Reference

### Format
```
<category>(<type>): <brief description>

<Detailed description>

Why: <Reasoning>

Impact: <How it affects the system>

Co-Authored-By: Claude <Model> <noreply@anthropic.com>
```

### Example
```
feat(storage): implement secret redaction before storage

Added SecretRedactor class to detect and redact sensitive information
including API keys, AWS credentials, GitHub tokens, and passwords.

Why: Step 1 requirement to never store unredacted secrets. Automatic
redaction prevents accidental exposure of credentials.

Impact: All user input is automatically redacted before storage.
Existing records unaffected.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

---

## Complete Guide

### 1. Commit Categories

| Category | Purpose | When to Use |
|----------|---------|------------|
| **feat** | New feature | Adding a new capability or tool |
| **core** | Core change | Significant architecture or core logic changes |
| **fix** | Bug fix | Fixing a defect or error |
| **test** | Tests | Adding or modifying tests |
| **docs** | Documentation | README, guides, comments |
| **refactor** | Cleanup | Code refactoring without changing behavior |
| **perf** | Performance | Optimization improvements |
| **chore** | Maintenance | Dependencies, config, build changes |
| **security** | Security | Security fixes or security-related changes |

### 2. Commit Types

Used to specify which module/component:

| Type | Module | Examples |
|------|--------|----------|
| `storage` | `core/storage.py` | Database operations, queries |
| `models` | `core/models.py` | SQLAlchemy model definitions |
| `services` | `core/services.py` | Business logic, API functions |
| `validation` | `core/validation.py` | Input validation rules |
| `redaction` | `core/redaction.py` | Secret detection and redaction |
| `config` | `core/config.py` | Configuration management |
| `mcp` | `mcp_server/` | MCP server and tools |
| `api` | `api/` | Django backend, REST API |
| `db` | Database | Migrations, schema changes |
| `test` | `test_*.py` | Test files and test infrastructure |

### 3. Title (First Line)

Requirements:
- **Format:** `<category>(<type>): <brief description>`
- **Length:** Maximum 50 characters
- **Mood:** Imperative ("add", "fix", "update" - NOT "added", "fixed")
- **Punctuation:** No period at end
- **Case:** Lowercase for category and type
- **Specificity:** Clear about what changed

**Good titles:**
```
feat(storage): implement secret redaction before storage
fix(validation): handle empty text fields correctly
core(models): add timezone-aware timestamps to all models
test(features): add validation and redaction tests
docs(readme): update setup instructions
refactor(services): simplify error handling
security(redaction): add SSH key detection
perf(storage): add database indexes
chore(config): migrate to environment variables
```

**Bad titles:**
```
added stuff                          # Too vague, past tense
fixed things                         # Not specific
update code                          # Unclear what changed
feat(storage): implement secret redaction before storing secrets in the database permanently  # Too long (>50 chars)
Fixed validation bugs in the input validation module  # Past tense, too long
```

### 4. Body (Detailed Description)

Required for all commits. Include:

#### What Changed
Describe the actual modifications:
```
Added SecretRedactor class with:
- Pattern matching for API keys, AWS credentials, GitHub tokens
- Recursive dictionary redaction support
- Safe regex error handling
```

#### Why Changed
Explain the reasoning:
```
Why: Step 1 requirement to never store unredacted secrets. Automatic
redaction on all write operations prevents accidental exposure of
credentials, API keys, or other sensitive information.
```

#### Impact
Describe consequences:
```
Impact: All user input is now automatically redacted before storage.
Existing data unaffected (no migration needed for Step 1 local-only
deployment). Zero performance overhead.
```

#### References
Link to related issues or PRs:
```
Fixes #42
Relates to #38
See also PR #45
```

#### Attribution
For AI-generated commits:
```
Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

### 5. Full Commit Examples

#### Example 1: Feature - Storage Implementation

```
feat(storage): implement secret redaction before storage

Added SecretRedactor class to detect and redact sensitive information
including API keys, AWS credentials, GitHub tokens, passwords, and
SSH private keys.

Features:
- Regex-based pattern matching for 6+ secret types
- Recursive redaction for dictionaries and lists
- Safe error handling for malformed patterns
- Applied automatically on all data write operations

Why: Step 1 requirement to prevent accidental storage of unredacted
secrets. Automatic redaction provides defense-in-depth security by
ensuring credentials never reach the database even if validation
is bypassed.

Impact: All user input is now automatically redacted before storage.
Zero performance overhead. Existing records unaffected. Secrets are
redacted as [REDACTED] in logs and storage.

Fixes #42
Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

#### Example 2: Bug Fix - Validation

```
fix(validation): handle empty text fields correctly

Fixed validation logic that was accepting empty strings after trimming.
The validate_text() function now properly rejects empty or whitespace-only
input with a clear error message.

Changes:
- Added check for zero-length strings after strip()
- Improved error message to indicate which field is empty
- Added tests for empty string edge cases

Why: Input validation must reject empty fields to maintain data quality.
Previous implementation allowed strings like "   " to pass validation
and be stored in the database.

Impact: All MCP tools now properly reject empty inputs. Error messages
clearly indicate which field is empty. No breaking changes to existing
valid inputs.

Fixes #156
Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

#### Example 3: Core - Database Models

```
core(models): add timezone-aware timestamps to all models

Updated all SQLAlchemy models (Project, Decision, State, Session) to use
UTC timezone-aware timestamps via datetime.now(UTC) instead of naive
datetime objects.

Changes:
- Imported UTC from datetime module
- Created utc_now() helper function
- Updated all created_at and updated_at columns to use utc_now
- Verified all timestamp columns use nullable=False

Why: Timezone-aware timestamps prevent bugs with DST transitions and
multi-region deployments. Follows Python and SQLAlchemy best practices.
Naive timestamps can lead to ambiguous time interpretation.

Impact: All new records use UTC timezone-aware timestamps. No migration
needed for existing data; SQLite interprets all timestamps as UTC
automatically. This is future-proofing for when Step 2 adds multi-region
support.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

#### Example 4: Test - Comprehensive Testing

```
test(features): add validation and redaction tests

Added comprehensive test suite (test_features.py, 120 lines) covering:
- Secret redaction (API keys, AWS AKIA, GitHub tokens)
- Input validation (type checking, length limits, empty field checks)
- Error handling (exception propagation, error logging)
- Integration tests (full flow from validation to storage)

Test Results:
✓ All redaction patterns working
✓ Validation rejects invalid inputs
✓ Errors logged and propagated correctly
✓ Integration tests pass

Why: Testing validates all safety features work correctly before merge.
Prevents regressions when features are modified. Ensures safety layer
integrity.

Impact: test_features.py now provides full coverage of validation,
redaction, and error handling layers. Developers can run `pytest` to
verify safety features before pushing changes.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

#### Example 5: Documentation

```
docs(readme): update setup instructions

Updated README.md setup section with:
- Step-by-step installation instructions
- Virtual environment creation
- Dependency installation with uv
- How to run tests
- How to start MCP server
- Connection instructions for Claude Code

Why: Current setup instructions were incomplete and outdated. New
developers were confused about how to get started. Clear instructions
reduce onboarding time.

Impact: New contributors can get up and running in < 5 minutes.
Reduced support questions about setup.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

---

## Creating a Commit

### Interactive Git Commit

```bash
# Stage your changes
git add .

# Verify what you're committing
git status
git diff --cached

# Create commit (opens editor with template)
git commit

# Verify the commit
git log --oneline -1
git show
```

### Command Line Commit

```bash
# Single line (title only - use for simple changes)
git commit -m "feat(storage): implement secret redaction before storage"

# Multi-line (title + body)
git commit -m "feat(storage): implement secret redaction before storage" \
           -m "Added SecretRedactor class..." \
           -m "Why: Step 1 requirement..."
```

### Using Commit Template

Set git to use template:
```bash
git config commit.template .claude/commit_template.txt
```

Then commits open editor with template:
```bash
git commit
```

---

## Commit Workflow Checklist

- [ ] Made your changes
- [ ] Tests passing: `pytest`
- [ ] Type checking: `mypy` (if enabled)
- [ ] Code linting: `ruff` (if enabled)
- [ ] Staged changes: `git add`
- [ ] Reviewed changes: `git diff --cached`
- [ ] Created commit with proper format
- [ ] Verified commit: `git show`
- [ ] Push to branch: `git push`

---

## Common Mistakes to Avoid

### ❌ Past Tense
```
❌ added secret redaction
❌ fixed validation bug
❌ updated configuration

✅ add secret redaction
✅ fix validation bug
✅ update configuration
```

### ❌ Too Long Title
```
❌ feat(storage): implement automatic secret redaction for all data write operations before storing to database
(This is 109 characters - way over 50!)

✅ feat(storage): implement secret redaction before storage
(47 characters - perfect!)
```

### ❌ No Body
```
❌ feat(storage): add redaction
(No explanation of why or impact!)

✅ feat(storage): add secret redaction
   
   Added SecretRedactor class...
   Why: Prevent accidental credential storage...
   Impact: All input is redacted...
```

### ❌ Vague Description
```
❌ fix: bug fixes
❌ feat: updates
❌ core: changes

✅ fix(validation): reject empty text fields
✅ feat(storage): add secret redaction
✅ core(models): add timezone-aware timestamps
```

### ❌ Multiple Unrelated Changes
```
❌ feat(storage): add redaction, update config, and fix validation
(Three different things - should be three commits!)

✅ Three separate commits:
   - feat(storage): add secret redaction
   - chore(config): migrate to environment variables
   - fix(validation): handle empty fields
```

---

## Tips for Good Commits

1. **Small, focused commits** - One feature/fix per commit
2. **Frequent commits** - Commit often, not once at the end
3. **Clear titles** - Anyone should understand what changed
4. **Detailed bodies** - Explain the reasoning
5. **Searchable** - Use specific keywords for future `git log` searches
6. **Properly attributed** - Include Co-Authored-By for AI-generated code

---

## Questions?

See `.claude/commit-skill.md` for detailed reference.

---

**Status:** ✅ Commit guide ready - standardized commits enabled
