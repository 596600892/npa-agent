from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "app.sqlite"
SECRET_FIELDS = {"api_key", "voice_api_key", "tts_api_key"}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects(
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              asset_type TEXT NOT NULL,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              latest_report_id TEXT
            );
            CREATE TABLE IF NOT EXISTS files(
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              filename TEXT NOT NULL,
              file_type TEXT NOT NULL,
              stored_path TEXT NOT NULL,
              sha256 TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS field_mappings(
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              file_id TEXT NOT NULL,
              mapping_json TEXT NOT NULL,
              confidence_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS loan_accounts(
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              row_number INTEGER NOT NULL,
              data_json TEXT NOT NULL,
              derived_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS analysis_reports(
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              version TEXT NOT NULL,
              markdown TEXT NOT NULL,
              data_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_logs(
              id TEXT PRIMARY KEY,
              project_id TEXT,
              event_type TEXT NOT NULL,
              event_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings(
              key TEXT PRIMARY KEY,
              value_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS skill_calls(
              id TEXT PRIMARY KEY,
              project_id TEXT,
              skill_name TEXT NOT NULL,
              permissions_json TEXT NOT NULL,
              input_summary_json TEXT NOT NULL,
              output_summary_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS intelligence_sources(
              id TEXT PRIMARY KEY,
              source_type TEXT NOT NULL,
              url TEXT,
              title TEXT,
              raw_text TEXT NOT NULL,
              raw_sha256 TEXT NOT NULL,
              fetched_at TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS yindeng_notices(
              id TEXT PRIMARY KEY,
              source_id TEXT,
              source_url TEXT,
              title TEXT NOT NULL,
              transferor TEXT,
              asset_type TEXT,
              debtor_count INTEGER,
              principal REAL,
              interest REAL,
              total_claim REAL,
              regions_json TEXT NOT NULL,
              dates_json TEXT NOT NULL,
              attachments_json TEXT NOT NULL,
              raw_text TEXT NOT NULL,
              parsed_json TEXT NOT NULL,
              confidence TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS yindeng_subscriptions(
              id TEXT PRIMARY KEY,
              keyword TEXT NOT NULL,
              enabled INTEGER NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS yindeng_alerts(
              id TEXT PRIMARY KEY,
              subscription_id TEXT NOT NULL,
              notice_id TEXT NOT NULL,
              keyword TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS model_calls(
              id TEXT PRIMARY KEY,
              project_id TEXT,
              provider TEXT NOT NULL,
              model TEXT NOT NULL,
              purpose TEXT NOT NULL,
              safety_mode TEXT NOT NULL,
              prompt_chars INTEGER NOT NULL,
              response_chars INTEGER NOT NULL,
              status TEXT NOT NULL,
              error TEXT,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS voice_calls(
              id TEXT PRIMARY KEY,
              provider TEXT NOT NULL,
              voice TEXT,
              text_chars INTEGER NOT NULL,
              status TEXT NOT NULL,
              error TEXT,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS secrets_meta(
              id TEXT PRIMARY KEY,
              scope TEXT NOT NULL,
              field TEXT NOT NULL,
              present INTEGER NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS company_history_files(
              id TEXT PRIMARY KEY,
              filename TEXT NOT NULL,
              stored_path TEXT NOT NULL,
              sha256 TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS company_history_mappings(
              id TEXT PRIMARY KEY,
              file_id TEXT NOT NULL,
              mapping_json TEXT NOT NULL,
              confidence_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS company_history_records(
              id TEXT PRIMARY KEY,
              batch_id TEXT NOT NULL,
              row_number INTEGER NOT NULL,
              data_json TEXT NOT NULL,
              derived_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS court_profiles(
              court_name TEXT PRIMARY KEY,
              profile_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pricing_calibrations(
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              calibration_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS legal_documents(
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              filename TEXT NOT NULL,
              file_type TEXT NOT NULL,
              stored_path TEXT NOT NULL,
              sha256 TEXT NOT NULL,
              extracted_text TEXT NOT NULL,
              parser_version TEXT NOT NULL,
              text_quality TEXT NOT NULL,
              warnings_json TEXT NOT NULL,
              page_count INTEGER,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS legal_risk_analyses(
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              document_id TEXT NOT NULL,
              risk_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS execution_plans(
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              name TEXT NOT NULL,
              version TEXT NOT NULL,
              status TEXT NOT NULL,
              summary_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS execution_batches(
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              plan_id TEXT NOT NULL,
              batch_key TEXT NOT NULL,
              name TEXT NOT NULL,
              tier TEXT NOT NULL,
              description TEXT NOT NULL,
              sort_order INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS execution_tasks(
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              plan_id TEXT NOT NULL,
              batch_id TEXT NOT NULL,
              account_id TEXT NOT NULL,
              tier TEXT NOT NULL,
              priority_score INTEGER NOT NULL,
              status TEXT NOT NULL,
              latest_result TEXT,
              latest_note TEXT,
              next_action TEXT NOT NULL,
              task_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS execution_events(
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              task_id TEXT NOT NULL,
              event_type TEXT NOT NULL,
              result TEXT,
              note TEXT,
              next_action TEXT,
              event_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS knowledge_notes(
              id TEXT PRIMARY KEY,
              note_type TEXT NOT NULL,
              scope_id TEXT,
              title TEXT NOT NULL,
              path TEXT NOT NULL,
              summary TEXT NOT NULL,
              tags_json TEXT NOT NULL,
              source_json TEXT NOT NULL,
              status TEXT NOT NULL,
              content_text TEXT NOT NULL,
              content_sha256 TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS private_skill_drafts(
              id TEXT PRIMARY KEY,
              draft_type TEXT NOT NULL,
              name TEXT NOT NULL,
              status TEXT NOT NULL,
              risk_level TEXT NOT NULL,
              manifest_text TEXT NOT NULL,
              markdown TEXT NOT NULL,
              path TEXT NOT NULL,
              source_note_ids_json TEXT NOT NULL,
              review_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )


def _secrets_path() -> Path:
    path = DATA_DIR / "secrets"
    path.mkdir(parents=True, exist_ok=True)
    return path / "settings.json"


def _load_secrets() -> dict:
    path = _secrets_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_secrets(data: dict) -> None:
    path = _secrets_path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def set_secret(scope: str, field: str, value: str | None) -> bool:
    secrets = _load_secrets()
    scoped = secrets.setdefault(scope, {})
    present = bool(value)
    if present:
        scoped[field] = value
    else:
        scoped.pop(field, None)
    if not scoped:
        secrets.pop(scope, None)
    _save_secrets(secrets)
    with connect() as conn:
        conn.execute(
            "INSERT INTO secrets_meta(id,scope,field,present,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET present=excluded.present, updated_at=excluded.updated_at",
            (f"{scope}:{field}", scope, field, int(present), now_iso()),
        )
    return present


def get_secret(scope: str, field: str) -> str | None:
    return _load_secrets().get(scope, {}).get(field)


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def insert_project(project: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO projects(id,name,asset_type,status,created_at,updated_at,latest_report_id) VALUES(?,?,?,?,?,?,?)",
            (project["id"], project["name"], project["asset_type"], project["status"], project["created_at"], project["updated_at"], project.get("latest_report_id")),
        )


def update_project(project_id: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = now_iso()
    assignments = ", ".join(f"{key}=?" for key in fields)
    values = list(fields.values()) + [project_id]
    with connect() as conn:
        conn.execute(f"UPDATE projects SET {assignments} WHERE id=?", values)


def get_project(project_id: str) -> dict | None:
    with connect() as conn:
        return row_to_dict(conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone())


def list_projects() -> list[dict]:
    with connect() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()]


def insert_file(record: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO files(id,project_id,filename,file_type,stored_path,sha256,created_at) VALUES(?,?,?,?,?,?,?)",
            (record["id"], record["project_id"], record["filename"], record["file_type"], record["stored_path"], record["sha256"], record["created_at"]),
        )


def get_file(file_id: str) -> dict | None:
    with connect() as conn:
        return row_to_dict(conn.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone())


def latest_file(project_id: str) -> dict | None:
    with connect() as conn:
        return row_to_dict(conn.execute("SELECT * FROM files WHERE project_id=? ORDER BY created_at DESC LIMIT 1", (project_id,)).fetchone())


def save_mapping(record: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO field_mappings(id,project_id,file_id,mapping_json,confidence_json,created_at) VALUES(?,?,?,?,?,?)",
            (record["id"], record["project_id"], record["file_id"], json.dumps(record["mapping"], ensure_ascii=False), json.dumps(record["confidence"], ensure_ascii=False), record["created_at"]),
        )


def latest_mapping(project_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM field_mappings WHERE project_id=? ORDER BY created_at DESC LIMIT 1", (project_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["mapping"] = json.loads(data.pop("mapping_json"))
        data["confidence"] = json.loads(data.pop("confidence_json"))
        return data


def replace_accounts(project_id: str, accounts: list[dict]) -> None:
    created = now_iso()
    with connect() as conn:
        conn.execute("DELETE FROM loan_accounts WHERE project_id=?", (project_id,))
        for account in accounts:
            derived = account.get("derived", {})
            conn.execute(
                "INSERT INTO loan_accounts(id,project_id,row_number,data_json,derived_json,created_at) VALUES(?,?,?,?,?,?)",
                (account["id"], project_id, account["row_number"], json.dumps(account, ensure_ascii=False), json.dumps(derived, ensure_ascii=False), created),
            )


def get_accounts(project_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT data_json FROM loan_accounts WHERE project_id=? ORDER BY row_number", (project_id,)).fetchall()
        return [json.loads(row["data_json"]) for row in rows]


def insert_report(report: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO analysis_reports(id,project_id,version,markdown,data_json,created_at) VALUES(?,?,?,?,?,?)",
            (report["id"], report["project_id"], report["version"], report["markdown"], json.dumps(report["data"], ensure_ascii=False), report["created_at"]),
        )
    update_project(report["project_id"], latest_report_id=report["id"], status="analyzed")


def latest_report(project_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM analysis_reports WHERE project_id=? ORDER BY created_at DESC LIMIT 1", (project_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["data"] = json.loads(data.pop("data_json"))
        return data


def get_setting(key: str, default: dict) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT value_json FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row["value_json"]) if row else default


def set_setting(key: str, value: dict) -> dict:
    stored = {**get_setting(key, {}), **value}
    for secret_key in SECRET_FIELDS:
        if secret_key in stored:
            stored[f"{secret_key}_present"] = set_secret(key, secret_key, stored.pop(secret_key))
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings(key,value_json,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
            (key, json.dumps(stored, ensure_ascii=False), now_iso()),
        )
    return stored


def insert_intelligence_source(record: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO intelligence_sources(id,source_type,url,title,raw_text,raw_sha256,fetched_at,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (record["id"], record["source_type"], record.get("url"), record.get("title"), record["raw_text"], record["raw_sha256"], record["fetched_at"], record["created_at"]),
        )


def insert_yindeng_notice(record: dict) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO yindeng_notices(
              id,source_id,source_url,title,transferor,asset_type,debtor_count,principal,interest,total_claim,
              regions_json,dates_json,attachments_json,raw_text,parsed_json,confidence,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                record["id"],
                record.get("source_id"),
                record.get("source_url"),
                record["title"],
                record.get("transferor"),
                record.get("asset_type"),
                record.get("debtor_count"),
                record.get("principal"),
                record.get("interest"),
                record.get("total_claim"),
                json.dumps(record.get("regions", []), ensure_ascii=False),
                json.dumps(record.get("dates", {}), ensure_ascii=False),
                json.dumps(record.get("attachments", []), ensure_ascii=False),
                record["raw_text"],
                json.dumps(record.get("parsed", {}), ensure_ascii=False),
                record.get("confidence", "low"),
                record["created_at"],
            ),
        )


def find_yindeng_notice_by_raw_sha(raw_sha256: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT n.* FROM yindeng_notices n
            JOIN intelligence_sources s ON s.id = n.source_id
            WHERE s.raw_sha256=?
            ORDER BY n.created_at DESC
            LIMIT 1
            """,
            (raw_sha256,),
        ).fetchone()
        return _notice_row(row) if row else None


def _notice_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["regions"] = json.loads(data.pop("regions_json"))
    data["dates"] = json.loads(data.pop("dates_json"))
    data["attachments"] = json.loads(data.pop("attachments_json"))
    data["parsed"] = json.loads(data.pop("parsed_json"))
    return data


def list_yindeng_notices() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM yindeng_notices ORDER BY created_at DESC LIMIT 100").fetchall()
        return [_notice_row(row) for row in rows]


def get_yindeng_notice(notice_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM yindeng_notices WHERE id=?", (notice_id,)).fetchone()
        return _notice_row(row) if row else None


def insert_yindeng_subscription(record: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO yindeng_subscriptions(id,keyword,enabled,created_at) VALUES(?,?,?,?)",
            (record["id"], record["keyword"], 1 if record.get("enabled", True) else 0, record["created_at"]),
        )


def list_yindeng_subscriptions(enabled_only: bool = False) -> list[dict]:
    query = "SELECT * FROM yindeng_subscriptions"
    params: tuple = ()
    if enabled_only:
        query += " WHERE enabled=1"
    query += " ORDER BY created_at DESC"
    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) | {"enabled": bool(row["enabled"])} for row in rows]


def insert_yindeng_alert(record: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO yindeng_alerts(id,subscription_id,notice_id,keyword,created_at) VALUES(?,?,?,?,?)",
            (record["id"], record["subscription_id"], record["notice_id"], record["keyword"], record["created_at"]),
        )


def list_yindeng_alerts() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT a.*, n.title, n.asset_type, n.principal, n.debtor_count, n.source_url
            FROM yindeng_alerts a
            JOIN yindeng_notices n ON n.id = a.notice_id
            ORDER BY a.created_at DESC
            LIMIT 100
            """
        ).fetchall()
        return [dict(row) for row in rows]


def insert_model_call(record: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO model_calls(id,project_id,provider,model,purpose,safety_mode,prompt_chars,response_chars,status,error,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                record["id"],
                record.get("project_id"),
                record["provider"],
                record["model"],
                record["purpose"],
                record["safety_mode"],
                record["prompt_chars"],
                record["response_chars"],
                record["status"],
                record.get("error"),
                record["created_at"],
            ),
        )


def insert_voice_call(record: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO voice_calls(id,provider,voice,text_chars,status,error,created_at) VALUES(?,?,?,?,?,?,?)",
            (record["id"], record["provider"], record.get("voice"), record["text_chars"], record["status"], record.get("error"), record["created_at"]),
        )


def insert_company_history_file(record: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO company_history_files(id,filename,stored_path,sha256,created_at) VALUES(?,?,?,?,?)",
            (record["id"], record["filename"], record["stored_path"], record["sha256"], record["created_at"]),
        )


def get_company_history_file(file_id: str) -> dict | None:
    with connect() as conn:
        return row_to_dict(conn.execute("SELECT * FROM company_history_files WHERE id=?", (file_id,)).fetchone())


def latest_company_history_file() -> dict | None:
    with connect() as conn:
        return row_to_dict(conn.execute("SELECT * FROM company_history_files ORDER BY created_at DESC LIMIT 1").fetchone())


def save_company_history_mapping(record: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO company_history_mappings(id,file_id,mapping_json,confidence_json,created_at) VALUES(?,?,?,?,?)",
            (record["id"], record["file_id"], json.dumps(record["mapping"], ensure_ascii=False), json.dumps(record["confidence"], ensure_ascii=False), record["created_at"]),
        )


def replace_company_history_records(batch_id: str, records: list[dict]) -> None:
    created = now_iso()
    with connect() as conn:
        conn.execute("DELETE FROM company_history_records WHERE batch_id=?", (batch_id,))
        for record in records:
            derived = record.get("derived", {})
            conn.execute(
                "INSERT INTO company_history_records(id,batch_id,row_number,data_json,derived_json,created_at) VALUES(?,?,?,?,?,?)",
                (record["id"], batch_id, record["row_number"], json.dumps(record, ensure_ascii=False), json.dumps(derived, ensure_ascii=False), created),
            )


def list_company_history_records(limit: int = 5000) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT data_json FROM company_history_records ORDER BY created_at DESC, row_number LIMIT ?", (limit,)).fetchall()
        return [json.loads(row["data_json"]) for row in rows]


def replace_court_profiles(profiles: list[dict]) -> None:
    updated = now_iso()
    with connect() as conn:
        conn.execute("DELETE FROM court_profiles")
        for profile in profiles:
            conn.execute(
                "INSERT INTO court_profiles(court_name,profile_json,updated_at) VALUES(?,?,?)",
                (profile["court_name"], json.dumps(profile, ensure_ascii=False), updated),
            )


def list_court_profiles() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT profile_json FROM court_profiles ORDER BY updated_at DESC, court_name").fetchall()
        return [json.loads(row["profile_json"]) for row in rows]


def get_court_profile(court_name: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT profile_json FROM court_profiles WHERE court_name=?", (court_name,)).fetchone()
        return json.loads(row["profile_json"]) if row else None


def insert_pricing_calibration(record: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO pricing_calibrations(id,project_id,calibration_json,created_at) VALUES(?,?,?,?)",
            (record["id"], record["project_id"], json.dumps(record["calibration"], ensure_ascii=False), record["created_at"]),
        )


def insert_legal_document(record: dict) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO legal_documents(
              id,project_id,filename,file_type,stored_path,sha256,extracted_text,parser_version,text_quality,warnings_json,page_count,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                record["id"],
                record["project_id"],
                record["filename"],
                record["file_type"],
                record["stored_path"],
                record["sha256"],
                record.get("extracted_text", ""),
                record["parser_version"],
                record["text_quality"],
                json.dumps(record.get("warnings", []), ensure_ascii=False),
                record.get("page_count"),
                record["created_at"],
            ),
        )


def _legal_document_row(row: sqlite3.Row, include_text: bool = False) -> dict:
    data = dict(row)
    data["warnings"] = json.loads(data.pop("warnings_json"))
    if not include_text:
        data.pop("extracted_text", None)
    return data


def get_legal_document(document_id: str, include_text: bool = False) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM legal_documents WHERE id=?", (document_id,)).fetchone()
        return _legal_document_row(row, include_text) if row else None


def list_legal_documents(project_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM legal_documents WHERE project_id=? ORDER BY created_at DESC", (project_id,)).fetchall()
        return [_legal_document_row(row) for row in rows]


def insert_legal_risk_analysis(record: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO legal_risk_analyses(id,project_id,document_id,risk_json,created_at) VALUES(?,?,?,?,?)",
            (record["id"], record["project_id"], record["document_id"], json.dumps(record["risk"], ensure_ascii=False), record["created_at"]),
        )


def latest_legal_risk(project_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM legal_risk_analyses WHERE project_id=? ORDER BY created_at DESC LIMIT 1", (project_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["risk"] = json.loads(data.pop("risk_json"))
        return data


def save_execution_plan(bundle: dict) -> None:
    plan = bundle["plan"]
    with connect() as conn:
        conn.execute("UPDATE execution_plans SET status='superseded' WHERE project_id=? AND status='active'", (plan["project_id"],))
        conn.execute(
            "INSERT INTO execution_plans(id,project_id,name,version,status,summary_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (plan["id"], plan["project_id"], plan["name"], plan["version"], plan["status"], json.dumps(plan["summary"], ensure_ascii=False), plan["created_at"]),
        )
        for batch in bundle["batches"]:
            conn.execute(
                "INSERT INTO execution_batches(id,project_id,plan_id,batch_key,name,tier,description,sort_order) VALUES(?,?,?,?,?,?,?,?)",
                (batch["id"], batch["project_id"], batch["plan_id"], batch["batch_key"], batch["name"], batch["tier"], batch["description"], batch["sort_order"]),
            )
        for task in bundle["tasks"]:
            conn.execute(
                """
                INSERT INTO execution_tasks(
                  id,project_id,plan_id,batch_id,account_id,tier,priority_score,status,latest_result,latest_note,next_action,task_json,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    task["id"],
                    task["project_id"],
                    task["plan_id"],
                    task["batch_id"],
                    task["account_id"],
                    task["tier"],
                    task["priority_score"],
                    task["status"],
                    task.get("latest_result"),
                    task.get("latest_note"),
                    task["next_action"],
                    json.dumps(task, ensure_ascii=False),
                    task["created_at"],
                    task["updated_at"],
                ),
            )


def _execution_plan_row(row: sqlite3.Row | None) -> dict | None:
    if not row:
        return None
    data = dict(row)
    data["summary"] = json.loads(data.pop("summary_json"))
    return data


def latest_execution_plan(project_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM execution_plans WHERE project_id=? ORDER BY created_at DESC LIMIT 1", (project_id,)).fetchone()
        return _execution_plan_row(row)


def list_execution_batches(project_id: str, plan_id: str | None = None) -> list[dict]:
    plan_id = plan_id or (latest_execution_plan(project_id) or {}).get("id")
    if not plan_id:
        return []
    with connect() as conn:
        rows = conn.execute("SELECT * FROM execution_batches WHERE project_id=? AND plan_id=? ORDER BY sort_order", (project_id, plan_id)).fetchall()
        return [dict(row) for row in rows]


def _execution_task_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    task = json.loads(data.pop("task_json"))
    task["status"] = data["status"]
    task["latest_result"] = data.get("latest_result")
    task["latest_note"] = data.get("latest_note")
    task["next_action"] = data["next_action"]
    task["updated_at"] = data["updated_at"]
    return task


def list_execution_tasks(project_id: str, plan_id: str | None = None, filters: dict | None = None) -> list[dict]:
    plan_id = plan_id or (latest_execution_plan(project_id) or {}).get("id")
    if not plan_id:
        return []
    filters = filters or {}
    clauses = ["project_id=?", "plan_id=?"]
    values: list[Any] = [project_id, plan_id]
    for key in ["batch_id", "status", "tier"]:
        if filters.get(key):
            clauses.append(f"{key}=?")
            values.append(filters[key])
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM execution_tasks WHERE {' AND '.join(clauses)} ORDER BY priority_score DESC, created_at",
            values,
        ).fetchall()
        return [_execution_task_row(row) for row in rows]


def get_execution_task(project_id: str, task_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM execution_tasks WHERE project_id=? AND id=?", (project_id, task_id)).fetchone()
        return _execution_task_row(row) if row else None


def update_execution_task(project_id: str, task_id: str, updates: dict) -> dict | None:
    current = get_execution_task(project_id, task_id)
    if not current:
        return None
    allowed = {"status", "latest_result", "latest_note", "next_action"}
    changed = {key: value for key, value in updates.items() if key in allowed}
    if not changed:
        return current
    current.update(changed)
    current["updated_at"] = now_iso()
    with connect() as conn:
        conn.execute(
            "UPDATE execution_tasks SET status=?, latest_result=?, latest_note=?, next_action=?, task_json=?, updated_at=? WHERE project_id=? AND id=?",
            (
                current["status"],
                current.get("latest_result"),
                current.get("latest_note"),
                current["next_action"],
                json.dumps(current, ensure_ascii=False),
                current["updated_at"],
                project_id,
                task_id,
            ),
        )
    return current


def insert_execution_event(record: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO execution_events(id,project_id,task_id,event_type,result,note,next_action,event_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                record["id"],
                record["project_id"],
                record["task_id"],
                record["event_type"],
                record.get("result"),
                record.get("note"),
                record.get("next_action"),
                json.dumps(record, ensure_ascii=False),
                record["created_at"],
            ),
        )


def list_execution_events(project_id: str, task_id: str | None = None) -> list[dict]:
    clauses = ["project_id=?"]
    values: list[Any] = [project_id]
    if task_id:
        clauses.append("task_id=?")
        values.append(task_id)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT event_json FROM execution_events WHERE {' AND '.join(clauses)} ORDER BY created_at DESC",
            values,
        ).fetchall()
        return [json.loads(row["event_json"]) for row in rows]


def upsert_knowledge_note(record: dict) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO knowledge_notes(
              id,note_type,scope_id,title,path,summary,tags_json,source_json,status,content_text,content_sha256,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              note_type=excluded.note_type,
              scope_id=excluded.scope_id,
              title=excluded.title,
              path=excluded.path,
              summary=excluded.summary,
              tags_json=excluded.tags_json,
              source_json=excluded.source_json,
              status=excluded.status,
              content_text=excluded.content_text,
              content_sha256=excluded.content_sha256,
              updated_at=excluded.updated_at
            """,
            (
                record["id"],
                record["note_type"],
                record.get("scope_id"),
                record["title"],
                record["path"],
                record["summary"],
                json.dumps(record.get("tags", []), ensure_ascii=False),
                json.dumps(record.get("source", {}), ensure_ascii=False),
                record.get("status", "confirmed"),
                record["content_text"],
                record["content_sha256"],
                record["created_at"],
                record["updated_at"],
            ),
        )


def _knowledge_note_row(row: sqlite3.Row, include_content: bool = False) -> dict:
    data = dict(row)
    data["tags"] = json.loads(data.pop("tags_json"))
    data["source"] = json.loads(data.pop("source_json"))
    if not include_content:
        data.pop("content_text", None)
    return data


def list_knowledge_notes(note_type: str | None = None, limit: int = 100) -> list[dict]:
    with connect() as conn:
        if note_type:
            rows = conn.execute("SELECT * FROM knowledge_notes WHERE note_type=? ORDER BY updated_at DESC LIMIT ?", (note_type, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM knowledge_notes ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [_knowledge_note_row(row) for row in rows]


def get_knowledge_note(note_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM knowledge_notes WHERE id=?", (note_id,)).fetchone()
        return _knowledge_note_row(row, include_content=True) if row else None


def search_knowledge_notes(query: str, limit: int = 50) -> list[dict]:
    term = f"%{query.lower()}%"
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM knowledge_notes
            WHERE lower(title) LIKE ? OR lower(summary) LIKE ? OR lower(content_text) LIKE ? OR lower(tags_json) LIKE ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (term, term, term, term, limit),
        ).fetchall()
        return [_knowledge_note_row(row) for row in rows]


def list_confirmed_knowledge_notes(note_types: set[str] | None = None, limit: int = 500) -> list[dict]:
    clauses = ["status='confirmed'"]
    values: list[Any] = []
    if note_types:
        placeholders = ",".join("?" for _ in note_types)
        clauses.append(f"note_type IN ({placeholders})")
        values.extend(sorted(note_types))
    values.append(limit)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM knowledge_notes WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT ?",
            values,
        ).fetchall()
        return [_knowledge_note_row(row, include_content=True) for row in rows]


def insert_private_skill_draft(record: dict) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO private_skill_drafts(
              id,draft_type,name,status,risk_level,manifest_text,markdown,path,source_note_ids_json,review_json,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                record["id"],
                record["draft_type"],
                record["name"],
                record["status"],
                record["risk_level"],
                record["manifest_text"],
                record["markdown"],
                record["path"],
                json.dumps(record.get("source_note_ids", []), ensure_ascii=False),
                json.dumps(record.get("review", {}), ensure_ascii=False),
                record["created_at"],
                record["updated_at"],
            ),
        )


def _private_skill_draft_row(row: sqlite3.Row | None) -> dict | None:
    if not row:
        return None
    data = dict(row)
    data["source_note_ids"] = json.loads(data.pop("source_note_ids_json"))
    data["review"] = json.loads(data.pop("review_json"))
    return data


def list_private_skill_drafts(status: str | None = None, draft_type: str | None = None, limit: int = 100) -> list[dict]:
    clauses: list[str] = []
    values: list[Any] = []
    if status:
        clauses.append("status=?")
        values.append(status)
    if draft_type:
        clauses.append("draft_type=?")
        values.append(draft_type)
    values.append(limit)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as conn:
        rows = conn.execute(f"SELECT * FROM private_skill_drafts {where} ORDER BY updated_at DESC LIMIT ?", values).fetchall()
        return [_private_skill_draft_row(row) for row in rows]


def get_private_skill_draft(draft_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM private_skill_drafts WHERE id=?", (draft_id,)).fetchone()
        return _private_skill_draft_row(row)


def update_private_skill_draft(draft_id: str, updates: dict) -> dict | None:
    current = get_private_skill_draft(draft_id)
    if not current:
        return None
    allowed = {"name", "status", "manifest_text", "markdown", "review"}
    changed = {key: value for key, value in updates.items() if key in allowed}
    if not changed:
        return current
    current.update(changed)
    current["updated_at"] = now_iso()
    with connect() as conn:
        conn.execute(
            """
            UPDATE private_skill_drafts
            SET name=?, status=?, manifest_text=?, markdown=?, review_json=?, updated_at=?
            WHERE id=?
            """,
            (
                current["name"],
                current["status"],
                current["manifest_text"],
                current["markdown"],
                json.dumps(current.get("review", {}), ensure_ascii=False),
                current["updated_at"],
                draft_id,
            ),
        )
    return current


def audit(project_id: str | None, event_type: str, event: dict) -> None:
    record_id = f"audit_{datetime.now(timezone.utc).timestamp():.6f}".replace(".", "_")
    with connect() as conn:
        conn.execute(
            "INSERT INTO audit_logs(id,project_id,event_type,event_json,created_at) VALUES(?,?,?,?,?)",
            (record_id, project_id, event_type, json.dumps(event, ensure_ascii=False), now_iso()),
        )
