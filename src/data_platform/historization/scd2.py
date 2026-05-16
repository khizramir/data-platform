import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class UpsertAction(str, Enum):
    INSERTED     = "inserted"
    UPDATED      = "updated"
    UNCHANGED    = "unchanged"
    LATE_ARRIVING = "late_arriving"


@dataclass
class HistorizedRecord:
    """A single version of a record in an SCD Type 2 store."""
    natural_key: dict[str, Any]
    attributes:  dict[str, Any]
    valid_from:  datetime
    valid_to:    datetime | None
    is_current:  bool
    record_hash: str

    @property
    def source_record(self) -> dict[str, Any]:
        return {**self.natural_key, **self.attributes}


@dataclass
class UpsertResult:
    action:           UpsertAction
    natural_key:      dict[str, Any]
    previous_version: HistorizedRecord | None
    new_version:      HistorizedRecord | None
    timestamp:        datetime


class SCD2Manager:
    """
    In-memory SCD Type 2 manager.

    Tracks full version history keyed by natural key fields.
    Change detection is hash-based (SHA-256 over sorted JSON attributes).
    Supports late-arriving data with chronological insertion.
    """

    def __init__(
        self,
        natural_key_fields: list[str],
        hash_exclude_fields: list[str] | None = None,
    ) -> None:
        self.natural_key_fields = list(natural_key_fields)
        self._hash_exclude = set(hash_exclude_fields or [])
        self._store: dict[str, list[HistorizedRecord]] = {}

    def upsert(self, record: dict[str, Any], timestamp: datetime | None = None) -> UpsertResult:
        ts      = timestamp or datetime.now(tz=timezone.utc)
        nk      = self._extract_natural_key(record)
        attrs   = self._extract_attributes(record)
        rh      = self._compute_hash(attrs)
        key     = self._key_str(nk)
        history = self._store.get(key, [])

        if not history:
            return self._insert(key, nk, attrs, rh, ts)

        current = self._current(history)

        if current is not None and ts < current.valid_from:
            return self._handle_late_arriving(key, history, nk, attrs, rh, ts)

        if current is not None and current.record_hash == rh:
            return UpsertResult(action=UpsertAction.UNCHANGED, natural_key=nk,
                                previous_version=current, new_version=current, timestamp=ts)

        return self._update(key, history, current, nk, attrs, rh, ts)

    def get_current(self, natural_key: dict[str, Any]) -> HistorizedRecord | None:
        return self._current(self._store.get(self._key_str(natural_key), []))

    def get_history(self, natural_key: dict[str, Any]) -> list[HistorizedRecord]:
        return list(self._store.get(self._key_str(natural_key), []))

    def get_version_at(self, natural_key: dict[str, Any], timestamp: datetime) -> HistorizedRecord | None:
        for version in reversed(self.get_history(natural_key)):
            if version.valid_from <= timestamp:
                if version.valid_to is None or version.valid_to > timestamp:
                    return version
        return None

    def count(self) -> int:
        return len(self._store)

    def total_versions(self) -> int:
        return sum(len(v) for v in self._store.values())

    def _extract_natural_key(self, record: dict[str, Any]) -> dict[str, Any]:
        missing = [f for f in self.natural_key_fields if f not in record]
        if missing:
            raise ValueError(f"Record missing natural key field(s): {missing}")
        return {f: record[f] for f in self.natural_key_fields}

    def _extract_attributes(self, record: dict[str, Any]) -> dict[str, Any]:
        exclude = set(self.natural_key_fields) | self._hash_exclude
        return {k: v for k, v in record.items() if k not in exclude}

    def _compute_hash(self, attributes: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(attributes, sort_keys=True, default=str).encode()
        ).hexdigest()

    def _key_str(self, natural_key: dict[str, Any]) -> str:
        return json.dumps({f: natural_key[f] for f in self.natural_key_fields},
                          sort_keys=True, default=str)

    @staticmethod
    def _current(history: list[HistorizedRecord]) -> HistorizedRecord | None:
        for rec in reversed(history):
            if rec.is_current:
                return rec
        return None

    def _insert(self, key, nk, attrs, rh, ts) -> UpsertResult:
        new = HistorizedRecord(natural_key=nk, attributes=attrs,
                               valid_from=ts, valid_to=None, is_current=True, record_hash=rh)
        self._store[key] = [new]
        return UpsertResult(action=UpsertAction.INSERTED, natural_key=nk,
                            previous_version=None, new_version=new, timestamp=ts)

    def _update(self, key, history, current, nk, attrs, rh, ts) -> UpsertResult:
        prev = current
        if current is not None:
            idx = history.index(current)
            history[idx] = HistorizedRecord(
                natural_key=current.natural_key, attributes=current.attributes,
                valid_from=current.valid_from, valid_to=ts,
                is_current=False, record_hash=current.record_hash)
        new = HistorizedRecord(natural_key=nk, attributes=attrs,
                               valid_from=ts, valid_to=None, is_current=True, record_hash=rh)
        history.append(new)
        self._store[key] = history
        return UpsertResult(action=UpsertAction.UPDATED, natural_key=nk,
                            previous_version=prev, new_version=new, timestamp=ts)

    def _handle_late_arriving(self, key, history, nk, attrs, rh, ts) -> UpsertResult:
        insert_idx = 0
        for i, rec in enumerate(history):
            if rec.valid_from <= ts:
                insert_idx = i + 1
            else:
                break
        valid_to = history[insert_idx].valid_from if insert_idx < len(history) else None
        new = HistorizedRecord(natural_key=nk, attributes=attrs,
                               valid_from=ts, valid_to=valid_to,
                               is_current=(valid_to is None), record_hash=rh)
        if insert_idx > 0:
            prev = history[insert_idx - 1]
            history[insert_idx - 1] = HistorizedRecord(
                natural_key=prev.natural_key, attributes=prev.attributes,
                valid_from=prev.valid_from, valid_to=ts,
                is_current=False, record_hash=prev.record_hash)
        history.insert(insert_idx, new)
        self._store[key] = history
        return UpsertResult(action=UpsertAction.LATE_ARRIVING, natural_key=nk,
                            previous_version=history[insert_idx - 1] if insert_idx > 0 else None,
                            new_version=new, timestamp=ts)
