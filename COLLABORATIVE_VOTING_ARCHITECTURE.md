# Collaborative Voting Architecture (Phase 1)

This document defines the hosted portal voting implementation for scaffold and molecule collaboration while preserving immutable release artifacts.

## 1. Database Design

Storage backend: SQLite (file-based) for initial deployment.

Database file:
- `HOSTED_PORTAL_VOTE_DB_PATH`
- default: `tmp/hosted_portal_data/votes.sqlite3`

Tables:

1. `users`
- `username TEXT PRIMARY KEY`
- `first_seen_at TEXT NOT NULL`
- `last_seen_at TEXT NOT NULL`

2. `scaffold_votes`
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `release_id TEXT NOT NULL`
- `scaffold_id TEXT NOT NULL`
- `username TEXT NOT NULL`
- `vote_type TEXT NOT NULL` (`LIKE`, `PRIORITY`, `REJECT`)
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `UNIQUE(release_id, scaffold_id, username)`

3. `molecule_votes`
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `release_id TEXT NOT NULL`
- `molecule_id TEXT NOT NULL`
- `username TEXT NOT NULL`
- `vote_type TEXT NOT NULL` (`LIKE`, `PRIORITY`, `REJECT`)
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `UNIQUE(release_id, molecule_id, username)`

4. `vote_events` (audit trail)
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `object_type TEXT NOT NULL` (`scaffold` or `molecule`)
- `release_id TEXT NOT NULL`
- `object_id TEXT NOT NULL`
- `username TEXT NOT NULL`
- `previous_vote_type TEXT`
- `vote_type TEXT NOT NULL`
- `created_at TEXT NOT NULL`

## 2. Service Layer Design

`VoteService` in `app/services/vote_service.py` encapsulates all vote persistence and query logic.

Core operations:
- Cast scaffold vote (`cast_scaffold_vote`)
- Cast molecule vote (`cast_molecule_vote`)
- Fetch object-level summaries with recent voters and user vote
- Fetch release-level vote summaries for polling
- Fetch user-specific vote activity
- Provide operational vote metrics for `/operations`

Design goals:
- One active vote per user per object (`UNIQUE` constraints + UPSERT)
- Update existing vote on re-vote
- Persist vote history in `vote_events`
- Keep storage independent from release artifacts

## 3. Flask Route Design

Blueprint: `app/api/votes.py`

Registered under `/api`.

Write routes:
- `POST /api/votes/scaffold`
- `POST /api/votes/molecule`

Read routes:
- `GET /api/votes/scaffold/<scaffold_id>`
- `GET /api/votes/molecule/<molecule_id>`
- `GET /api/votes/release/<release_id>`
- `GET /api/votes/users/<username>`

## 4. API Schemas

### POST /api/votes/scaffold
Request JSON:
```json
{
  "release_id": "release_20260803_001",
  "scaffold_id": "SCF-015",
  "username": "John Eksterowicz",
  "vote_type": "LIKE"
}
```

Response JSON:
```json
{
  "vote": {
    "release_id": "release_20260803_001",
    "scaffold_id": "SCF-015",
    "username": "John Eksterowicz",
    "vote_type": "LIKE",
    "created_at": "2026-08-02T...Z",
    "updated_at": "2026-08-02T...Z"
  },
  "summary": {
    "release_id": "release_20260803_001",
    "scaffold_id": "SCF-015",
    "counts": { "LIKE": 7, "PRIORITY": 3, "REJECT": 1 },
    "total": 11,
    "recent_voters": ["John", "Monika", "Thomas"],
    "user_vote": "LIKE",
    "updated_at": "2026-08-02T...Z",
    "history": []
  }
}
```

### POST /api/votes/molecule
Request JSON:
```json
{
  "release_id": "release_20260803_001",
  "molecule_id": "EN300-5002668_27207",
  "username": "Monika Williams",
  "vote_type": "PRIORITY"
}
```

Response JSON mirrors scaffold response with `molecule_id`.

### GET /api/votes/scaffold/<scaffold_id>
Query params:
- `release_id` (required)
- `username` (optional)

Returns summary + recent vote history for scaffold.

### GET /api/votes/molecule/<molecule_id>
Query params:
- `release_id` (required)
- `username` (optional)

Returns summary + recent vote history for molecule.

### GET /api/votes/release/<release_id>
Query params:
- `username` (optional)
- `scaffold_ids` CSV (optional)
- `molecule_ids` CSV (optional)

Returns:
- `scaffold_votes` map keyed by scaffold id
- `molecule_votes` map keyed by molecule id
- `meta` section with returned object counts

### GET /api/votes/users/<username>
Query params:
- `release_id` (optional)
- `limit` (optional, default 200)

Returns user-level scaffold and molecule votes.

## 5. Frontend Polling Implementation

Entry point: `app/static/js/portal.js`

Behavior:
1. On report page load, identify hosted report iframe.
2. Prompt once for `Enter Your Name` (if not already in local storage).
3. Inject compact vote widgets into:
   - scaffold cards (`.idea-card[data-scaffold]`)
   - molecule tiles (`.moltile[data-mol-id]`)
4. Submit votes via API POST endpoints.
5. Poll release summary every `HOSTED_PORTAL_VOTE_POLL_SECONDS` (default 5).
6. Refresh counts, current user selection, and recent voters in-place.

No report redesign is required. Existing scaffold layout and molecular viewer behavior remain intact.

## 6. Report Integration Strategy

Integration location: wrapper page `app/templates/release.html`.

Approach:
- Preserve existing generated static report in iframe (authoritative content).
- Add data attributes to iframe for vote endpoints and polling interval.
- Enhance report DOM in-place after iframe load.

Benefits:
- Zero mutation of release artifacts.
- No disruption to filtering, docking viewer, or export controls.

## 7. Migration Plan

Phase 1 (implemented):
- SQLite with service abstraction (`VoteService`).
- API contract independent of SQLite-specific SQL semantics.

Phase 2 (future):
- Implement `PostgresVoteService` with same method signatures.
- Bind service via config switch:
  - `HOSTED_PORTAL_VOTE_BACKEND=sqlite|postgres`
- Preserve API response contracts and frontend behavior.

## 8. Storage and Retention Strategy

- Vote data stored in dedicated DB file outside release directories.
- Release artifacts remain immutable and vote-independent.
- Vote DB survives browser refresh, Flask restart, and server restart.

Initial retention:
- Keep complete vote history indefinitely.
- Add scheduled archival/retention in future for very large histories.

## 9. Operations Metrics Integration

`/operations` now surfaces voting telemetry:
- Total Votes
- Scaffold Votes
- Molecule Votes
- Active Users
- Most Liked Scaffolds
- Most Rejected Scaffolds
- Most Prioritized Scaffolds
- Most Liked Molecules

Metrics source:
- `VoteService.get_operations_metrics()`
- merged in `OperationsService.get_metrics()`

## 10. Testing Plan

Automated tests in `tests/test_voting_api.py`:
- One active vote per user per scaffold, with updates on revote
- Cross-user polling payload behavior
- Vote persistence across app restart

Manual validation workflow:
1. Scientist A opens `/release/<release_id>/report`.
2. Scientist A votes on scaffold.
3. Scientist B opens same report and sees update within one polling cycle.
4. Scientist B votes on molecule.
5. Scientist A sees molecule update within one polling cycle.
6. Refresh browser and restart app; votes remain present.

## Configuration

New environment variables:
- `HOSTED_PORTAL_VOTE_DB_PATH` (path to SQLite DB)
- `HOSTED_PORTAL_VOTE_POLL_SECONDS` (polling interval, default `5`)
