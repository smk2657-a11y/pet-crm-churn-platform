
import os
import sqlite3
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import streamlit as st

from .paths import DB_PATH
from .storage import get_user_membership_status, record_login_history

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALG = "HS256"
JWT_EXPIRE_HOURS = 8


def _get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def _apply_membership_to_session(username: str):
    status = get_user_membership_status(username)
    st.session_state["user_key"] = username
    st.session_state["pro_paid"] = bool(status.get("is_pro", False))
    st.session_state["service_mode"] = status.get("service_mode", "free")
    st.session_state["pro_expires_at"] = status.get("pro_expires_at")
    st.session_state["pro_days_left"] = status.get("days_left", 0)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def create_jwt(user_key: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_key,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=JWT_EXPIRE_HOURS)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_jwt(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    except Exception:
        return None


def restore_auth_from_session():
    token = st.session_state.get("auth_token")
    if not token:
        st.session_state["user_key"] = "guest"
        st.session_state["service_mode"] = "free"
        st.session_state["pro_paid"] = False
        st.session_state["pro_expires_at"] = None
        st.session_state["pro_days_left"] = 0
        return

    payload = decode_jwt(token)
    if not payload:
        st.session_state["auth_token"] = None
        st.session_state["user_key"] = "guest"
        st.session_state["service_mode"] = "free"
        st.session_state["pro_paid"] = False
        st.session_state["pro_expires_at"] = None
        st.session_state["pro_days_left"] = 0
        return

    _apply_membership_to_session(payload.get("sub", "guest"))


def logout_user():
    st.session_state["auth_token"] = None
    st.session_state["user_key"] = "guest"
    st.session_state["service_mode"] = "free"
    st.session_state["pro_paid"] = False
    st.session_state["pro_expires_at"] = None
    st.session_state["pro_days_left"] = 0


def signup_user(username: str, password: str) -> tuple[bool, str]:
    username = (username or "").strip()
    password = password or ""

    if not username:
        return False, "아이디를 입력해주세요."
    if len(password) < 4:
        return False, "비밀번호는 4자 이상 입력해주세요."

    conn = _get_conn()
    cur = conn.cursor()

    try:
        cur.execute("SELECT 1 FROM users WHERE username = ?", (username,))
        if cur.fetchone():
            return False, "이미 존재하는 아이디입니다."

        pw_hash = hash_password(password)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur.execute(
            """
            INSERT INTO users (username, password_hash, created_at, is_pro, pro_expires_at, last_login_at)
            VALUES (?, ?, ?, 0, NULL, NULL)
            """,
            (username, pw_hash, created_at),
        )
        conn.commit()
        return True, "회원가입이 완료되었습니다."
    except Exception as e:
        return False, f"회원가입 중 오류가 발생했습니다: {e}"
    finally:
        conn.close()


def login_user(username: str, password: str) -> tuple[bool, str, str | None]:
    username = (username or "").strip()
    password = password or ""

    if not username or not password:
        return False, "아이디와 비밀번호를 입력해주세요.", None

    conn = _get_conn()
    cur = conn.cursor()

    try:
        cur.execute(
            "SELECT username, password_hash FROM users WHERE username = ?",
            (username,),
        )
        row = cur.fetchone()

        if not row:
            record_login_history(username, False, "user_not_found")
            return False, "아이디 또는 비밀번호가 올바르지 않습니다.", None

        db_username, password_hash = row
        if not verify_password(password, password_hash):
            record_login_history(db_username, False, "wrong_password")
            return False, "아이디 또는 비밀번호가 올바르지 않습니다.", None

        token = create_jwt(db_username)
        record_login_history(db_username, True, "login_success")
        return True, "로그인 성공", token
    except Exception as e:
        try:
            record_login_history(username, False, f"login_error:{e}")
        except Exception:
            pass
        return False, f"로그인 중 오류가 발생했습니다: {e}", None
    finally:
        conn.close()


def login_gate():
    st.markdown("### 로그인")
    username = st.text_input("아이디", key="login_username")
    password = st.text_input("비밀번호", type="password", key="login_password")

    submitted = st.button("로그인 실행", type="primary", use_container_width=True, key="login_submit_btn")

    if not submitted:
        return False, None, None

    ok, msg, token = login_user(username, password)
    if not ok:
        st.error(msg)
        return False, None, None

    st.session_state["auth_token"] = token
    payload = decode_jwt(token)
    user_key = payload["sub"] if payload else username
    _apply_membership_to_session(user_key)
    return True, user_key, user_key


def signup_form():
    st.markdown("### 회원가입")
    username = st.text_input("아이디", key="signup_username")
    password = st.text_input("비밀번호", type="password", key="signup_password")
    password2 = st.text_input("비밀번호 확인", type="password", key="signup_password2")

    submitted = st.button("회원가입 실행", type="primary", use_container_width=True, key="signup_submit_btn")

    if not submitted:
        return

    if password != password2:
        st.error("비밀번호 확인이 일치하지 않습니다.")
        return

    ok, msg = signup_user(username, password)
    if ok:
        st.success(msg)
    else:
        st.error(msg)
