# Changelog: DEV Branch vs ABCo (Production)

Date: 2026-06-08
Comparison: `origin/ABCo` (production) → `HEAD` (`claude/practical-cori-hrNlu`)
Stats: 33 files changed, 589 insertions, 664 deletions

---

## 1. Core Refactoring (Major Changes)

### pbx/core/pbx.py — Type Safety & Concurrency Hardening (+447 lines changed)

- **Type annotations overhaul**: Added `from __future__ import annotations`, `TYPE_CHECKING` imports for 50+ feature/integration types, and explicit type hints on all 40+ class attributes.
- **Per-extension registration locking**: Added `_registration_locks` dict with `threading.Lock` per extension to prevent race conditions during concurrent REGISTER messages. `register_extension()` now acquires a per-extension lock before delegating to `_register_extension_locked()`. **(Fixes #636)**
- **Pre-compiled regex patterns**: Moved inline regex compilation to module-level constants (`_RE_SIP_EXT`, `_RE_MAC_PARAM`, `_RE_SIP_INSTANCE`, `_RE_MAC_IN_UA`), eliminating per-call recompilation overhead. **(Partially addresses #635 item 7)**
- **Defensive MAC/UA parsing**: `_extract_mac_address()` and `_detect_phone_model()` now wrapped in try-except to handle malformed SIP headers gracefully. **(Fixes #638)**
- **Null safety improvements**: Replaced `hasattr()` checks with explicit `is not None` comparisons. Added `str()`/`bool()` coercions for config values.
- **Metrics check**: Changed from falsy checks to explicit `None` checks in `_metrics_collection_loop()`.

### pbx/core/call.py — Memory Leak Fix & Thread Safety

- **Bounded call history**: Replaced unbounded `list` with `deque(maxlen=MAX_HISTORY_SIZE)`, preventing memory leaks in long-running systems. **(Fixes #637)**
- **Thread-safe call management**: Added `threading.Lock()` around `active_calls` dictionary mutations (`create_call`, `end_call`).
- **Simplified cleanup**: Removed manual list trimming logic — `deque` maxlen handles this automatically.

### pbx/sip/server.py — Thread Pool Replacement

- **Bounded thread pool**: Replaced unbounded `threading.Thread()` spawning with `ThreadPoolExecutor(max_workers=200)` to prevent thread exhaustion under high SIP load. **(Fixes #635 item 1)**
- **Proper shutdown**: Added `_thread_pool.shutdown(wait=False)` in `stop()` method.
- **Simplified Via NAT logic**: Collapsed nested `if` into single condition (`SIM102` lint fix).

---

## 2. API & Feature Changes

### API Routes

- **Flask/Werkzeug compatibility**: Moved `Response` import from `flask` to `werkzeug.wrappers` in `compat.py` and `static.py` (required for Flask 3.1+).
- **Security route null checks**: Added `if not allowed and error_response is not None` guards across MFA, DND, and voicemail endpoints in `security.py` to prevent `None` reference errors.
- **Voicemail route fixes**: Added null safety checks in `voicemail.py`.

### Feature Modules

| Module | Change |
|--------|--------|
| `extensions.py` | Added `get_address()` method for SIP address retrieval |
| `phone_book.py` | Type hint fix: `extension_registry: str` → `Any` |
| `webhooks.py` | Added `CALL_TRANSFERRED` event type constant |
| `webrtc.py` | Defensive null checks for CDR/voicemail systems with early returns |
| `call_recording_analytics.py` | Added `confidence` field (0.0) to sentiment analysis output |

### Utils

- **config.py**: Added `@overload` decorators on `Config.get()` for better type inference. Import modernization.
- **database.py**: Replaced try/except with `contextlib.suppress()`. Type hint improvements. Simplified boolean logic.

---

## 3. Frontend Changes (admin/)

- **SBC Management tab removed**: Entire "Warden SBC" section deleted from `admin/dist/index.html` (197 lines — stats, config forms, relay tables, IP blacklist/whitelist, NAT detection).
- **TypeScript 6.x compat**: Added `"ignoreDeprecations": "6.0"` to `tsconfig.json`.
- **Vite config cleanup**: Removed explicit `cssMinify: true` (default in newer Vite).
- **JS module cleanup**: Removed `import './pages/sbc-management.ts'` from main.js. Removed global window function exposures from `auto_attendant.js` and `opensource_integrations.js`.
- **API endpoint fixes**: Corrected conversational-ai (`/statistics` → `/stats`) and voice-biometrics (`/profile/` → `/profiles/`) endpoints in `framework_features.js`.
- **WebRTC simplification**: Removed 60-second ringback safety timeout logic from `webrtc_phone.js`.
- **Rebuilt dist assets**: CSS and JS bundles regenerated with new hashes.

---

## 4. Dependency Bumps (Major Version Changes)

| Package | ABCo Version | Current Version | Severity |
|---------|-------------|-----------------|----------|
| twisted | 25.5.0 | 26.4.0 | **Major** |
| cryptography | 46.0.5 | 48.0.0 | **Major (+2)** |
| av | 16.1.0 | 17.1.0 | **Major** |
| mypy | 1.19.1 | 2.1.0 | **Major** |
| redis | 7.2.1 | 8.0.0 | **Major** |
| typescript | 5.9.3 | 6.0.3 | **Major** |
| vite | 7.3.3 | 8.0.12 | **Major** |
| ruff | 0.15.4 | 0.15.16 | Minor |
| prometheus-client | 0.24.1 | 0.25.0 | Minor |
| requests | 2.32.5 | 2.34.2 | Minor |

---

## 5. CI/CD & Tooling

- **dependency-updates.yml**: Downgraded action versions (checkout v6→v4, setup-python v6→v5, setup-node v6→v4, setup-uv v7→v8, create-pull-request v8→v7).
- **security-scanning.yml**: Enhanced Gitleaks with explicit options (`fail-on-warning: false`, `log-level: info`) and SARIF artifact upload for GitHub security dashboard.
- **.gitignore**: Added `data/` for runtime-generated files.

---

## 6. Open Issues Status

| Issue | Title | Status |
|-------|-------|--------|
| #635 | Performance & scalability risks | **Partially fixed** (thread pool, regex precompilation). Remaining: blocking DB calls, device detection caching, RTP lock contention, table scans, metrics. |
| #636 | Race condition in extension registration | **Fixed** (per-extension locking) |
| #637 | Unbounded call history memory leak | **Fixed** (deque with maxlen) |
| #638 | Unhandled exception in SIP MAC/UA parsing | **Fixed** (try-except wrapping) |
| #639 | Missing error handling for RTP port allocation failure during transfer | **Open** — needs implementation |

---

## 7. Risk Assessment

### Low Risk
- Dependency bumps (mostly automated, with lockfile updates)
- Type annotation additions (no behavioral change)
- Lint/format fixes

### Medium Risk
- SBC Management tab removal (verify no production references)
- Flask → Werkzeug Response import (verify all Flask versions in use)
- Thread pool max_workers=200 limit (may need tuning for specific deployments)

### High Risk (Behavioral Changes)
- Per-extension registration locking (new concurrency behavior)
- deque maxlen on call history (oldest calls silently dropped)
- Regex error suppression in MAC extraction (errors now silent instead of propagating)
