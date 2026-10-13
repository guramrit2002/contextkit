# Spec: Private Repository Support

**Project:** contextkit  
**Owner:** Guramrit  
**Status:** Draft  
**Priority:** High  

---

## 1. Background

Currently, contextkit only supports creating API keys for **public repositories**. Users who want to store context for private projects cannot use contextkit.

This blocks adoption among teams working on closed-source code.

---

## 2. Goal

Enable users to create contextkit API keys for **private repositories** they own, in addition to public ones.

**Success criteria:**
- User can sign in via GitHub and see both public and private repos
- User can create an API key for a private repo
- Contextkit MCP server works with private repos (no code changes needed)

---

## 3. What needs to change

### 3.1 Frontend (React) — `web/src/oauth.ts`

**Current:**
```typescript
// Line 49-54: No scope parameter
const params = new URLSearchParams({
  client_id: githubClientId(),
  redirect_uri: redirectUri(),
  state,
  allow_signup: 'true',
})
```

**Change to:**
```typescript
const params = new URLSearchParams({
  client_id: githubClientId(),
  redirect_uri: redirectUri(),
  state,
  allow_signup: 'true',
  scope: 'repo',  // Full repository access (public & private)
})
```

**Files affected:**
- `web/src/oauth.ts` (line 53)

---

### 3.2 Backend (Django) — `api/accounts/github.py`

**Current:**
- `list_public_repos(login)` — lists only public repos
- `fetch_public_repo(full_name)` — fetches only public repos

**Change to:**
- Rename `list_public_repos()` → `list_repos()` (or add new function)
- Rename `fetch_public_repo()` → `fetch_repo()` (or add new function)
- Both should work with private repos when user has `repo` scope

**Files affected:**
- `api/accounts/github.py`
- `api/accounts/services.py` (calls `fetch_public_repo`)
- `api/clients/services.py` (calls `fetch_public_repo`)

---

### 3.3 Error messages — `api/clients/services.py`

**Current:**
```python
NOT_YOUR_REPO_MESSAGE = "You can only create keys for public repositories you own on GitHub."
```

**Change to:**
```python
NOT_YOUR_REPO_MESSAGE = "You can only create keys for repositories you own on GitHub."
```

**Also update docstring** (line ~34):
```python
def ensure_owns_on_github(user, project_id: str) -> None:
    """
    The user must own the repository on GitHub, and it can be public or private (ADR 031).
    ...
    """
```

---

### 3.4 Architecture Decision Records (ADRs)

**Amend:**
- **ADR 028** — "No OAuth scope required" → Update to reflect `repo` scope is now needed
- **ADR 030** — "GitHub OAuth without scope" → Update to reflect scope change
- **ADR 031** — "Public repositories only" → Amend to "Public or private repositories"

---

## 4. Implementation order

1. **Update ADRs** (ADR 028, 030, 031) — document the decision
2. **Frontend** — add `scope: 'repo'` to authorization URL (`web/src/oauth.ts`)
3. **Backend — GitHub integration** — rename `fetch_public_repo()` → `fetch_repo()` and make it work with private repos
4. **Backend — API** — update error messages and docstrings
5. **Tests** — update test mocks and test cases to include private repos
6. **Update README** — change "public repositories" to "repositories"

---

## 5. Testing

### Manual testing:
- [ ] Sign in with GitHub using an account that owns private repos
- [ ] Verify the repository picker shows both public and private repos
- [ ] Create an API key for a private repo
- [ ] Verify the key works (call `get_context`)

### Automated testing:
- [ ] Update `test_owner_creates_a_key_for_their_public_repo` to also test private repos
- [ ] Update test mocks (`api/clients/testing.py`) to include private repos
- [ ] Test that the private repo is correctly validated as owned by the user

---

## 6. Backwards compatibility

- **No breaking changes.** Public repos continue to work as before.
- GitHub OAuth scope change: users will see a new permission request (to access private repos), which is expected and one-time.

---

## 7. Definition of done

- [ ] ADRs updated (028, 030, 031)
- [ ] `scope: 'repo'` added to authorization URL
- [ ] `fetch_public_repo()` → `fetch_repo()` (or new function)
- [ ] Error messages updated (remove "public")
- [ ] All tests pass
- [ ] Manual testing of private repo key creation works
- [ ] README updated
- [ ] Merged to `dev`

---

## 8. Open questions

- Should we show organization repositories, or only personal repos?
- Should we validate that the user is an owner, or any write permission?
- Should we add a test fixture for private repos to the mock?
