import sqlite3
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


VALID_VOTE_TYPES = ("LIKE", "PRIORITY", "REJECT")
SCAFFOLD_VOTE_TYPES = VALID_VOTE_TYPES
MOLECULE_VOTE_TYPES = VALID_VOTE_TYPES


class VoteValidationError(ValueError):
    pass


LOGGER = logging.getLogger("hosted_portal.votes")


class VoteService:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def cast_scaffold_vote(self, release_id, scaffold_id, username, vote_type):
        return self._cast_vote(
            table_name="scaffold_votes",
            object_type="scaffold",
            object_field="scaffold_id",
            allowed_vote_types=SCAFFOLD_VOTE_TYPES,
            release_id=release_id,
            object_id=scaffold_id,
            username=username,
            vote_type=vote_type,
        )

    def cast_molecule_vote(self, release_id, molecule_id, username, vote_type):
        return self._cast_vote(
            table_name="molecule_votes",
            object_type="molecule",
            object_field="molecule_id",
            allowed_vote_types=MOLECULE_VOTE_TYPES,
            release_id=release_id,
            object_id=molecule_id,
            username=username,
            vote_type=vote_type,
        )

    def get_scaffold_summary(self, release_id, scaffold_id, username=None):
        self._validate_id("release_id", release_id)
        self._validate_id("scaffold_id", scaffold_id)
        if username:
            username = self._normalize_username(username)

        rows = self._fetch_vote_rows(
            table_name="scaffold_votes",
            object_field="scaffold_id",
            release_id=release_id,
            object_ids=[scaffold_id],
        )
        summary_map = self._build_summary_map(rows, username=username, object_field="scaffold_id")
        summary = summary_map.get(scaffold_id, self._empty_summary(scaffold_id, username))
        summary["release_id"] = release_id
        summary["scaffold_id"] = scaffold_id
        summary["history"] = self._fetch_vote_history("scaffold", release_id, scaffold_id)
        return summary

    def get_molecule_summary(self, release_id, molecule_id, username=None):
        self._validate_id("release_id", release_id)
        self._validate_id("molecule_id", molecule_id)
        if username:
            username = self._normalize_username(username)

        rows = self._fetch_vote_rows(
            table_name="molecule_votes",
            object_field="molecule_id",
            release_id=release_id,
            object_ids=[molecule_id],
        )
        summary_map = self._build_summary_map(rows, username=username, object_field="molecule_id")
        summary = summary_map.get(molecule_id, self._empty_summary(molecule_id, username))
        summary["release_id"] = release_id
        summary["molecule_id"] = molecule_id
        summary["history"] = self._fetch_vote_history("molecule", release_id, molecule_id)
        return summary

    def get_release_summary(self, release_id, username=None, scaffold_ids=None, molecule_ids=None):
        self._validate_id("release_id", release_id)
        if username:
            username = self._normalize_username(username)

        scaffold_ids = self._normalize_id_list(scaffold_ids)
        molecule_ids = self._normalize_id_list(molecule_ids)

        scaffold_rows = self._fetch_vote_rows(
            table_name="scaffold_votes",
            object_field="scaffold_id",
            release_id=release_id,
            object_ids=scaffold_ids,
        )
        molecule_rows = self._fetch_vote_rows(
            table_name="molecule_votes",
            object_field="molecule_id",
            release_id=release_id,
            object_ids=molecule_ids,
        )

        scaffold_summaries = self._build_summary_map(
            scaffold_rows,
            username=username,
            object_field="scaffold_id",
        )
        molecule_summaries = self._build_summary_map(
            molecule_rows,
            username=username,
            object_field="molecule_id",
        )

        return {
            "release_id": release_id,
            "scaffold_votes": scaffold_summaries,
            "molecule_votes": molecule_summaries,
            "meta": {
                "scaffold_count": len(scaffold_summaries),
                "molecule_count": len(molecule_summaries),
                "username": username or "",
            },
        }

    def get_user_votes(self, username, release_id=None, limit=200):
        username = self._normalize_username(username)
        if release_id:
            self._validate_id("release_id", release_id)

        limit = max(1, min(2000, int(limit)))
        with self._connect() as conn:
            params = [username]
            release_filter = ""
            if release_id:
                release_filter = " AND release_id = ?"
                params.append(release_id)

            scaffold_rows = conn.execute(
                (
                    "SELECT release_id, scaffold_id AS object_id, vote_type, created_at, updated_at "
                    "FROM scaffold_votes WHERE username = ?"
                    f"{release_filter} ORDER BY updated_at DESC LIMIT ?"
                ),
                tuple(params + [limit]),
            ).fetchall()

            molecule_rows = conn.execute(
                (
                    "SELECT release_id, molecule_id AS object_id, vote_type, created_at, updated_at "
                    "FROM molecule_votes WHERE username = ?"
                    f"{release_filter} ORDER BY updated_at DESC LIMIT ?"
                ),
                tuple(params + [limit]),
            ).fetchall()

        return {
            "username": username,
            "release_id": release_id or "",
            "scaffold_votes": [
                {
                    "release_id": row["release_id"],
                    "scaffold_id": row["object_id"],
                    "vote_type": row["vote_type"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in scaffold_rows
            ],
            "molecule_votes": [
                {
                    "release_id": row["release_id"],
                    "molecule_id": row["object_id"],
                    "vote_type": row["vote_type"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in molecule_rows
            ],
        }

    def list_release_votes(self, release_id):
        self._validate_id("release_id", release_id)
        with self._connect() as conn:
            scaffold_rows = conn.execute(
                (
                    "SELECT release_id, 'scaffold' AS object_type, scaffold_id AS object_id, "
                    "vote_type, username, created_at, updated_at "
                    "FROM scaffold_votes WHERE release_id = ?"
                ),
                (release_id,),
            ).fetchall()

            molecule_rows = conn.execute(
                (
                    "SELECT release_id, 'molecule' AS object_type, molecule_id AS object_id, "
                    "vote_type, username, created_at, updated_at "
                    "FROM molecule_votes WHERE release_id = ?"
                ),
                (release_id,),
            ).fetchall()

        out = []
        for row in list(scaffold_rows) + list(molecule_rows):
            out.append(
                {
                    "release_id": row["release_id"],
                    "object_type": row["object_type"],
                    "object_id": row["object_id"],
                    "vote_type": row["vote_type"],
                    "username": row["username"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return out

    def get_release_consensus(self, release_id, threshold_n=3, scaffold_ids=None, molecule_ids=None):
        threshold_n = self._normalize_threshold(threshold_n)
        payload = self.get_release_summary(
            release_id=release_id,
            username=None,
            scaffold_ids=scaffold_ids,
            molecule_ids=molecule_ids,
        )

        scaffold_votes = payload.get("scaffold_votes") or {}
        molecule_votes = payload.get("molecule_votes") or {}

        scaffold_consensus = {}
        molecule_consensus = {}

        scaffold_positive_ids = []
        molecule_positive_ids = []

        for scaffold_id, summary in scaffold_votes.items():
            entry = self._consensus_entry(scaffold_id, "scaffold", summary, threshold_n)
            scaffold_consensus[scaffold_id] = entry
            if entry["consensus_positive"]:
                scaffold_positive_ids.append(scaffold_id)

        for molecule_id, summary in molecule_votes.items():
            entry = self._consensus_entry(molecule_id, "molecule", summary, threshold_n)
            molecule_consensus[molecule_id] = entry
            if entry["consensus_positive"]:
                molecule_positive_ids.append(molecule_id)

        return {
            "release_id": release_id,
            "consensus_threshold_n": threshold_n,
            "scaffolds": scaffold_consensus,
            "molecules": molecule_consensus,
            "consensus_scaffold_ids": sorted(scaffold_positive_ids),
            "consensus_molecule_ids": sorted(molecule_positive_ids),
        }

    def get_operations_metrics(self, limit=10):
        limit = max(1, min(50, int(limit)))
        with self._connect() as conn:
            total_scaffold_votes = conn.execute("SELECT COUNT(*) FROM scaffold_votes").fetchone()[0]
            total_molecule_votes = conn.execute("SELECT COUNT(*) FROM molecule_votes").fetchone()[0]
            total_votes = total_scaffold_votes + total_molecule_votes

            active_users = conn.execute(
                (
                    "SELECT COUNT(*) FROM ("
                    "SELECT username FROM scaffold_votes "
                    "UNION "
                    "SELECT username FROM molecule_votes"
                    ")"
                )
            ).fetchone()[0]

            def top_items(table_name, object_field, vote_type):
                rows = conn.execute(
                    (
                        f"SELECT release_id, {object_field} AS object_id, COUNT(*) AS count "
                        f"FROM {table_name} WHERE vote_type = ? "
                        f"GROUP BY release_id, {object_field} "
                        "ORDER BY count DESC, release_id, object_id LIMIT ?"
                    ),
                    (vote_type, limit),
                ).fetchall()
                return [
                    {
                        "release_id": row["release_id"],
                        "object_id": row["object_id"],
                        "count": row["count"],
                    }
                    for row in rows
                ]

            most_liked_scaffolds = top_items("scaffold_votes", "scaffold_id", "LIKE")
            most_rejected_scaffolds = top_items("scaffold_votes", "scaffold_id", "REJECT")
            most_prioritized_scaffolds = top_items("scaffold_votes", "scaffold_id", "PRIORITY")
            most_liked_molecules = top_items("molecule_votes", "molecule_id", "LIKE")

        return {
            "total_votes": total_votes,
            "total_scaffold_votes": total_scaffold_votes,
            "total_molecule_votes": total_molecule_votes,
            "active_users": active_users,
            "most_liked_scaffolds": most_liked_scaffolds,
            "most_rejected_scaffolds": most_rejected_scaffolds,
            "most_prioritized_scaffolds": most_prioritized_scaffolds,
            "most_liked_molecules": most_liked_molecules,
        }

    def health_snapshot(self):
        payload = {
            "db_path": str(self.db_path),
            "db_exists": self.db_path.exists(),
            "db_size_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0,
            "status": "healthy",
            "error": "",
        }
        try:
            with self._connect() as conn:
                row = conn.execute("PRAGMA quick_check").fetchone()
                quick_check = str(row[0] if row else "ok")
                table_rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            tables = set([r["name"] for r in table_rows])
            required = {"users", "scaffold_votes", "molecule_votes", "vote_events"}
            missing = sorted(required - tables)
            payload["quick_check"] = quick_check
            payload["tables_present"] = sorted(tables)
            payload["missing_tables"] = missing
            if quick_check.lower() != "ok" or missing:
                payload["status"] = "degraded"
        except Exception as exc:
            payload["status"] = "unhealthy"
            payload["error"] = str(exc)
            LOGGER.exception("Vote database health check failed")
        return payload

    def _cast_vote(self, table_name, object_type, object_field, allowed_vote_types, release_id, object_id, username, vote_type):
        self._validate_id("release_id", release_id)
        self._validate_id(object_field, object_id)
        username = self._normalize_username(username)
        vote_type = self._normalize_vote_type(vote_type, allowed_vote_types)

        now_iso = self._utcnow_iso()
        with self._connect() as conn:
            conn.execute(
                (
                    "INSERT INTO users (username, first_seen_at, last_seen_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(username) DO UPDATE SET last_seen_at = excluded.last_seen_at"
                ),
                (username, now_iso, now_iso),
            )

            prior = conn.execute(
                (
                    f"SELECT vote_type, created_at FROM {table_name} "
                    f"WHERE release_id = ? AND {object_field} = ? AND username = ?"
                ),
                (release_id, object_id, username),
            ).fetchone()

            created_at = prior["created_at"] if prior else now_iso
            prior_vote_type = prior["vote_type"] if prior else None

            conn.execute(
                (
                    f"INSERT INTO {table_name} (release_id, {object_field}, username, vote_type, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    f"ON CONFLICT(release_id, {object_field}, username) DO UPDATE SET "
                    "vote_type = excluded.vote_type, "
                    "updated_at = excluded.updated_at"
                ),
                (release_id, object_id, username, vote_type, created_at, now_iso),
            )

            conn.execute(
                (
                    "INSERT INTO vote_events (object_type, release_id, object_id, username, previous_vote_type, vote_type, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)"
                ),
                (object_type, release_id, object_id, username, prior_vote_type, vote_type, now_iso),
            )

        vote_payload = {
            "release_id": release_id,
            object_field: object_id,
            "username": username,
            "vote_type": vote_type,
            "created_at": created_at,
            "updated_at": now_iso,
        }

        LOGGER.info(
            "Vote recorded",
            extra={
                "event": "vote_recorded",
                "object_type": object_type,
                "release_id": release_id,
                "object_id": object_id,
                "username": username,
                "vote_type": vote_type,
            },
        )
        return vote_payload

    def _fetch_vote_rows(self, table_name, object_field, release_id, object_ids=None):
        clauses = ["release_id = ?"]
        params = [release_id]

        if object_ids:
            placeholders = ",".join(["?"] * len(object_ids))
            clauses.append(f"{object_field} IN ({placeholders})")
            params.extend(object_ids)

        query = (
            f"SELECT release_id, {object_field}, username, vote_type, created_at, updated_at "
            f"FROM {table_name} WHERE {' AND '.join(clauses)}"
        )

        with self._connect() as conn:
            return conn.execute(query, tuple(params)).fetchall()

    def _consensus_entry(self, object_id, object_type, summary, threshold_n):
        counts = summary.get("counts") or {}
        voters_by_type = summary.get("voters_by_type") or {}

        positive_users = set()
        for key in ("LIKE", "PRIORITY"):
            for username in voters_by_type.get(key) or []:
                positive_users.add(str(username))

        reject_users = set([str(username) for username in (voters_by_type.get("REJECT") or [])])

        high_priority_voters = set([str(username) for username in (voters_by_type.get("PRIORITY") or [])])
        like_voters = set([str(username) for username in (voters_by_type.get("LIKE") or [])])

        return {
            "object_type": object_type,
            "object_id": object_id,
            "like_count": int(counts.get("LIKE") or 0),
            "high_priority_count": int(counts.get("PRIORITY") or 0),
            "reject_count": int(counts.get("REJECT") or 0),
            "positive_unique_user_count": len(positive_users),
            "reject_unique_user_count": len(reject_users),
            "high_priority_unique_user_count": len(high_priority_voters),
            "like_unique_user_count": len(like_voters),
            "consensus_positive": (len(positive_users) >= threshold_n and int(counts.get("REJECT") or 0) == 0),
            "consensus_threshold_n": threshold_n,
        }

    def _build_summary_map(self, rows, username=None, object_field="object_id"):
        grouped = defaultdict(list)
        for row in rows:
            grouped[row[object_field]].append(row)

        summary = {}
        for object_id, entries in grouped.items():
            entries.sort(key=lambda item: item["updated_at"], reverse=True)
            counts = {vote_type: 0 for vote_type in VALID_VOTE_TYPES}
            voters_by_type = dict((vote_type, []) for vote_type in VALID_VOTE_TYPES)
            recent_voters = []
            seen_voters = set()
            user_vote = ""
            for entry in entries:
                vote_type = entry["vote_type"]
                if vote_type in counts:
                    counts[vote_type] += 1
                voter = entry["username"]
                if vote_type in voters_by_type:
                    voters_by_type[vote_type].append(voter)
                if voter not in seen_voters and len(recent_voters) < 5:
                    recent_voters.append(voter)
                    seen_voters.add(voter)
                if username and voter == username:
                    user_vote = vote_type

            summary[object_id] = {
                "counts": counts,
                "total": sum(counts.values()),
                "recent_voters": recent_voters,
                "voters_by_type": voters_by_type,
                "user_vote": user_vote,
                "updated_at": entries[0]["updated_at"],
            }

        return summary

    def _fetch_vote_history(self, object_type, release_id, object_id, limit=50):
        with self._connect() as conn:
            rows = conn.execute(
                (
                    "SELECT username, previous_vote_type, vote_type, created_at "
                    "FROM vote_events WHERE object_type = ? AND release_id = ? AND object_id = ? "
                    "ORDER BY id DESC LIMIT ?"
                ),
                (object_type, release_id, object_id, limit),
            ).fetchall()
        return [
            {
                "username": row["username"],
                "previous_vote_type": row["previous_vote_type"] or "",
                "vote_type": row["vote_type"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _initialize_schema(self):
        with self._connect() as conn:
            conn.execute(
                (
                    "CREATE TABLE IF NOT EXISTS users ("
                    "username TEXT PRIMARY KEY,"
                    "first_seen_at TEXT NOT NULL,"
                    "last_seen_at TEXT NOT NULL"
                    ")"
                )
            )
            conn.execute(
                (
                    "CREATE TABLE IF NOT EXISTS scaffold_votes ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "release_id TEXT NOT NULL,"
                    "scaffold_id TEXT NOT NULL,"
                    "username TEXT NOT NULL,"
                    "vote_type TEXT NOT NULL,"
                    "created_at TEXT NOT NULL,"
                    "updated_at TEXT NOT NULL,"
                    "UNIQUE(release_id, scaffold_id, username),"
                    "FOREIGN KEY(username) REFERENCES users(username)"
                    ")"
                )
            )
            conn.execute(
                (
                    "CREATE TABLE IF NOT EXISTS molecule_votes ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "release_id TEXT NOT NULL,"
                    "molecule_id TEXT NOT NULL,"
                    "username TEXT NOT NULL,"
                    "vote_type TEXT NOT NULL,"
                    "created_at TEXT NOT NULL,"
                    "updated_at TEXT NOT NULL,"
                    "UNIQUE(release_id, molecule_id, username),"
                    "FOREIGN KEY(username) REFERENCES users(username)"
                    ")"
                )
            )
            conn.execute(
                (
                    "CREATE TABLE IF NOT EXISTS vote_events ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "object_type TEXT NOT NULL,"
                    "release_id TEXT NOT NULL,"
                    "object_id TEXT NOT NULL,"
                    "username TEXT NOT NULL,"
                    "previous_vote_type TEXT,"
                    "vote_type TEXT NOT NULL,"
                    "created_at TEXT NOT NULL"
                    ")"
                )
            )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_scaffold_votes_release_scaffold ON scaffold_votes(release_id, scaffold_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_scaffold_votes_type ON scaffold_votes(vote_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_molecule_votes_release_molecule ON molecule_votes(release_id, molecule_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_molecule_votes_type ON molecule_votes(vote_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vote_events_lookup ON vote_events(object_type, release_id, object_id, created_at)"
            )

    def _normalize_vote_type(self, vote_type, allowed_vote_types=VALID_VOTE_TYPES):
        normalized = str(vote_type or "").strip().upper()
        if normalized not in allowed_vote_types:
            raise VoteValidationError(
                "vote_type must be one of " + ", ".join(allowed_vote_types)
            )
        return normalized

    def _normalize_username(self, username):
        normalized = str(username or "").strip()
        if not normalized:
            raise VoteValidationError("username is required")
        if len(normalized) > 120:
            raise VoteValidationError("username is too long (max 120 characters)")
        return normalized

    def _validate_id(self, field_name, value):
        normalized = str(value or "").strip()
        if not normalized:
            raise VoteValidationError(f"{field_name} is required")

    def _normalize_id_list(self, values):
        if not values:
            return []
        normalized = []
        for value in values:
            item = str(value or "").strip()
            if item:
                normalized.append(item)
        return normalized

    def _empty_summary(self, object_id, username=None):
        return {
            "id": object_id,
            "counts": {vote_type: 0 for vote_type in VALID_VOTE_TYPES},
            "total": 0,
            "recent_voters": [],
            "voters_by_type": dict((vote_type, []) for vote_type in VALID_VOTE_TYPES),
            "user_vote": "" if username else "",
            "updated_at": "",
        }

    def _normalize_threshold(self, threshold_n):
        try:
            value = int(threshold_n)
        except Exception:
            value = 3
        return max(1, min(100, value))

    def _utcnow_iso(self):
        return datetime.now(timezone.utc).isoformat()
