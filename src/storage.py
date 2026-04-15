
import json
import math
import sqlite3
import uuid
from datetime import date, datetime, timedelta

from .paths import DB_PATH


def _get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_column(cur, table: str, column: str, ddl: str):
    cur.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cur.fetchall()]
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_db():
    conn = _get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    _ensure_column(cur, "users", "is_pro", "is_pro INTEGER NOT NULL DEFAULT 0")
    _ensure_column(cur, "users", "pro_expires_at", "pro_expires_at TEXT")
    _ensure_column(cur, "users", "last_login_at", "last_login_at TEXT")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_key TEXT NOT NULL,
            run_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metrics_json TEXT,
            report_json TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS login_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            login_at TEXT NOT NULL,
            success INTEGER NOT NULL DEFAULT 0,
            message TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_key TEXT UNIQUE NOT NULL,
            username TEXT NOT NULL,
            payer_name TEXT,
            email TEXT,
            plan TEXT NOT NULL,
            amount REAL,
            status TEXT NOT NULL,
            paid_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()


def _parse_dt(value):
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        try:
            return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None


def sync_user_pro_status(username: str | None = None) -> None:
    conn = _get_conn()
    cur = conn.cursor()
    now = _now_str()

    if username:
        cur.execute(
            """
            UPDATE users
            SET is_pro = CASE
                WHEN pro_expires_at IS NOT NULL AND datetime(pro_expires_at) >= datetime(?) THEN 1
                ELSE 0
            END
            WHERE username = ?
            """,
            (now, username),
        )
    else:
        cur.execute(
            """
            UPDATE users
            SET is_pro = CASE
                WHEN pro_expires_at IS NOT NULL AND datetime(pro_expires_at) >= datetime(?) THEN 1
                ELSE 0
            END
            """,
            (now,),
        )

    conn.commit()
    conn.close()


def record_login_history(username: str, success: bool, message: str = "") -> None:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO login_history (username, login_at, success, message)
        VALUES (?, ?, ?, ?)
        """,
        (username, _now_str(), 1 if success else 0, message or ""),
    )
    if success:
        cur.execute(
            "UPDATE users SET last_login_at = ? WHERE username = ?",
            (_now_str(), username),
        )
    conn.commit()
    conn.close()


def get_user_membership_status(username: str) -> dict:
    if not username:
        return {"is_pro": False, "service_mode": "free", "pro_expires_at": None, "days_left": 0}

    sync_user_pro_status(username)

    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT is_pro, pro_expires_at, last_login_at FROM users WHERE username = ?",
        (username,),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return {"is_pro": False, "service_mode": "free", "pro_expires_at": None, "days_left": 0}

    is_pro, pro_expires_at, last_login_at = row
    exp_dt = _parse_dt(pro_expires_at)
    now = datetime.now()
    days_left = 0
    if exp_dt and exp_dt >= now:
        days_left = max(0, math.ceil((exp_dt - now).total_seconds() / 86400))

    active = bool(is_pro) and exp_dt is not None and exp_dt >= now
    return {
        "is_pro": active,
        "service_mode": "pro" if active else "free",
        "pro_expires_at": pro_expires_at,
        "days_left": days_left,
        "last_login_at": last_login_at,
    }


def activate_pro_membership(
    username: str,
    payer_name: str,
    email: str,
    plan: str = "pro_monthly",
    amount: float = 29000.0,
    duration_days: int = 30,
) -> dict:
    if not username:
        raise ValueError("로그인 사용자 정보가 없습니다.")

    conn = _get_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT pro_expires_at FROM users WHERE username = ?",
        (username,),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError("존재하지 않는 사용자입니다.")

    now = datetime.now()
    current_exp = _parse_dt(row[0])
    base_dt = current_exp if current_exp and current_exp > now else now
    new_exp = base_dt + timedelta(days=duration_days)

    payment_key = f"pay_{uuid.uuid4().hex[:20]}"
    paid_at = _now_str()
    expires_at = new_exp.strftime("%Y-%m-%d %H:%M:%S")

    cur.execute(
        """
        INSERT INTO payments (
            payment_key, username, payer_name, email, plan, amount, status,
            paid_at, expires_at, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payment_key,
            username,
            payer_name,
            email,
            plan,
            float(amount or 0),
            "paid",
            paid_at,
            expires_at,
            _now_str(),
        ),
    )

    cur.execute(
        """
        UPDATE users
        SET is_pro = 1,
            pro_expires_at = ?
        WHERE username = ?
        """,
        (expires_at, username),
    )

    conn.commit()
    conn.close()

    return {
        "payment_key": payment_key,
        "paid_at": paid_at,
        "expires_at": expires_at,
        "duration_days": duration_days,
    }


def list_payment_history(username: str) -> list[dict]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT payment_key, plan, amount, status, paid_at, expires_at, payer_name, email
        FROM payments
        WHERE username = ?
        ORDER BY datetime(created_at) DESC, id DESC
        """,
        (username,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "payment_key": r[0],
            "plan": r[1],
            "amount": r[2],
            "status": r[3],
            "paid_at": r[4],
            "expires_at": r[5],
            "payer_name": r[6],
            "email": r[7],
        }
        for r in rows
    ]


def _json_safe(obj):
    """
    json.dumps 전에 직렬화 불가능한 값을 안전하게 변환
    - datetime/date -> ISO 문자열
    - pandas.Timestamp -> 문자열
    - numpy number/bool -> 파이썬 기본형
    - NaN/NaT -> None
    - dict/list/tuple/set -> 재귀 변환
    """
    if obj is None:
        return None

    # 기본형
    if isinstance(obj, (str, int, bool)):
        return obj

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj

    # datetime / date
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()

    # dict
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}

    # list-like
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v) for v in obj]

    # pandas / numpy 대응
    try:
        import pandas as pd

        if pd.isna(obj):
            return None

        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()

        if isinstance(obj, pd.Timedelta):
            return str(obj)
    except Exception:
        pass

    try:
        import numpy as np

        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            val = float(obj)
            if math.isnan(val) or math.isinf(val):
                return None
            return val
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return [_json_safe(v) for v in obj.tolist()]
    except Exception:
        pass

    # 마지막 fallback
    return str(obj)


def save_run(user_key: str, run_name: str, metrics: dict, report: dict) -> int:
    conn = _get_conn()
    cur = conn.cursor()

    created_at = _now_str()
    metrics_json = json.dumps(_json_safe(metrics or {}), ensure_ascii=False)
    report_json = json.dumps(_json_safe(report or {}), ensure_ascii=False)

    cur.execute(
        """
        INSERT INTO runs (user_key, run_name, created_at, metrics_json, report_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_key, run_name, created_at, metrics_json, report_json),
    )
    conn.commit()
    run_id = cur.lastrowid
    conn.close()
    return run_id


def list_runs(user_key: str) -> list[dict]:
    conn = _get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, user_key, run_name, created_at, metrics_json
        FROM runs
        WHERE user_key = ?
        ORDER BY datetime(created_at) DESC, id DESC
        """,
        (user_key,),
    )
    rows = cur.fetchall()
    conn.close()

    items = []
    for row in rows:
        run_id, owner, run_name, created_at, metrics_json = row
        try:
            metrics = json.loads(metrics_json) if metrics_json else {}
        except Exception:
            metrics = {}

        items.append(
            {
                "run_id": run_id,
                "user_key": owner,
                "run_name": run_name,
                "created_at": created_at,
                "metrics": metrics,
            }
        )
    return items


def get_run(user_key: str, run_id: int) -> dict | None:
    conn = _get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, user_key, run_name, created_at, metrics_json, report_json
        FROM runs
        WHERE id = ? AND user_key = ?
        """,
        (run_id, user_key),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    rid, owner, run_name, created_at, metrics_json, report_json = row

    try:
        metrics = json.loads(metrics_json) if metrics_json else {}
    except Exception:
        metrics = {}

    try:
        report = json.loads(report_json) if report_json else {}
    except Exception:
        report = {}

    return {
        "run_id": rid,
        "user_key": owner,
        "run_name": run_name,
        "created_at": created_at,
        "metrics": metrics,
        "report": report,
    }


def delete_run(user_key: str, run_id: int) -> bool:
    conn = _get_conn()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM runs WHERE id = ? AND user_key = ?",
        (run_id, user_key),
    )
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted
