"""Application extensions, including a small Mongo-compatible local store.

The local store keeps development and smoke-test environments usable when MongoDB
is not installed.  The route layer can continue using ``mongo.db.collection``.
"""

import copy
import json
import os
import threading
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from flask_mail import Mail
from flask_session import Session
from flask_pymongo import PyMongo
from bson import ObjectId


class _JsonEncoder(json.JSONEncoder):
    def default(self, value):
        if isinstance(value, (datetime, date)):
            return {"__type__": "datetime", "value": value.isoformat()}
        if isinstance(value, ObjectId):
            return {"__type__": "objectid", "value": str(value)}
        return super().default(value)


def _decode(value):
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if isinstance(value, dict):
        if value.get("__type__") == "datetime":
            return datetime.fromisoformat(value["value"])
        if value.get("__type__") == "objectid":
            return ObjectId(value["value"])
        return {key: _decode(item) for key, item in value.items()}
    return value


def _matches(document, query):
    return all(document.get(key) == value for key, value in query.items())


class LocalCollection:
    def __init__(self, database, name):
        self.database = database
        self.name = name

    @property
    def _documents(self):
        return self.database.documents.setdefault(self.name, [])

    def find_one(self, query):
        with self.database.lock:
            for document in self._documents:
                if _matches(document, query):
                    return copy.deepcopy(document)
        return None

    def find(self, query=None, sort=None, limit=0):
        query = query or {}
        with self.database.lock:
            result = [copy.deepcopy(doc) for doc in self._documents if _matches(doc, query)]
        if sort:
            for field, direction in reversed(sort):
                result.sort(key=lambda doc: doc.get(field), reverse=direction < 0)
        return result[:limit] if limit else result

    def insert_one(self, document):
        with self.database.lock:
            item = copy.deepcopy(document)
            item.setdefault("_id", ObjectId())
            self._documents.append(item)
            self.database.save()
            return SimpleNamespace(inserted_id=item["_id"])

    def delete_many(self, query):
        with self.database.lock:
            original = len(self._documents)
            self.database.documents[self.name] = [
                doc for doc in self._documents if not _matches(doc, query)
            ]
            self.database.save()
            return SimpleNamespace(deleted_count=original - len(self.database.documents[self.name]))

    def update_one(self, query, update):
        with self.database.lock:
            document = next((doc for doc in self._documents if _matches(doc, query)), None)
            if document is None:
                return SimpleNamespace(matched_count=0, modified_count=0)
            for field, value in update.get("$set", {}).items():
                document[field] = copy.deepcopy(value)
            for field, value in update.get("$push", {}).items():
                document.setdefault(field, []).append(copy.deepcopy(value))
            self.database.save()
            return SimpleNamespace(matched_count=1, modified_count=1)


class LocalDatabase:
    def __init__(self, path=None, mode="file"):
        self.path = Path(path or "data/placementai_fallback.json")
        self.mode = mode
        self.lock = threading.RLock()
        self.documents = {}
        if self.mode == "file" and self.path.exists():
            try:
                self.documents = _decode(json.loads(self.path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                self.documents = {}

    def __getattr__(self, collection_name):
        return LocalCollection(self, collection_name)

    def save(self):
        if self.mode != "file":
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.documents, cls=_JsonEncoder, indent=2), encoding="utf-8")


class StorageExtension:
    """Use MongoDB when reachable, otherwise transparently use local storage."""

    def __init__(self):
        self._mongo = PyMongo()
        self._db = None
        self.using_fallback = False
        self.reason = ""

    def init_app(self, app):
        self.using_fallback = False
        self.reason = ""
        self._db = None
        uri = (app.config.get("MONGO_URI") or "").strip()
        if not uri:
            self._use_fallback(app, "MONGO_URI is not configured")
            return
        try:
            if not uri.startswith(("mongodb://", "mongodb+srv://")):
                raise ValueError("MONGO_URI must start with mongodb:// or mongodb+srv://")
            self._mongo.init_app(app)
            self._mongo.cx.admin.command("ping")
            self._db = self._mongo.db
        except Exception as exc:
            self._use_fallback(app, f"MongoDB unavailable: {exc.__class__.__name__}")

    def _use_fallback(self, app, reason):
        self.using_fallback = True
        self.reason = reason
        self._db = LocalDatabase(
            app.config.get("FALLBACK_STORAGE_PATH"),
            app.config.get("FALLBACK_STORAGE_MODE", "file"),
        )

    @property
    def db(self):
        return self._db


mongo = StorageExtension()
mail = Mail()
sess = Session()
