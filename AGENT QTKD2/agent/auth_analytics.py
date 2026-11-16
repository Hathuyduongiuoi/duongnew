"""Zero-dependency User Authentication (PBKDF2 + HMAC cookie, unique username/display_name/phone, OTP reset) & Role-based Analytics."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
_STORAGE_DIR = Path("/tmp/htd_data") if os.environ.get("VERCEL") else ROOT_DIR
if os.environ.get("VERCEL"):
    _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
USERS_FILE = _STORAGE_DIR / "users.json"
ANALYTICS_FILE = _STORAGE_DIR / "analytics_events.jsonl"
SETTINGS_FILE = _STORAGE_DIR / "site_settings.json"
SECRET_FILE = _STORAGE_DIR / ".session_secret"

_LOCK = threading.Lock()
_OTP_STORE: Dict[str, Dict[str, Any]] = {}  # phone -> {"code": str, "exp": float}

SESSION_COOKIE_NAME = "htd_session"
SESSION_TTL_SEC = 30 * 24 * 3600

OWNER_PHONES = {"0332125570"}
OWNER_USERNAMES = {"htd24307@gmail.com", "hathuyduong", "hathuyduong2403"}


def _get_secret() -> bytes:
    env_sec = os.environ.get("SESSION_SECRET", "").strip()
    if env_sec:
        return env_sec.encode("utf-8")
    with _LOCK:
        if SECRET_FILE.is_file():
            raw = SECRET_FILE.read_text(encoding="utf-8").strip()
            if raw:
                return raw.encode("utf-8")
        sec = secrets.token_hex(32)
        SECRET_FILE.write_text(sec, encoding="utf-8")
        return sec.encode("utf-8")


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("84") and len(digits) in (11, 12):
        digits = "0" + digits[2:]
    return digits


def _load_users() -> List[Dict[str, Any]]:
    if not USERS_FILE.is_file():
        return []
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_users(users: List[Dict[str, Any]]) -> None:
    USERS_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")


def hash_password(password: str, salt_hex: Optional[str] = None) -> str:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"pbkdf2_sha256${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, _ = stored.split("$", 2)
        if algo != "pbkdf2_sha256":
            return False
        actual = hash_password(password, salt_hex=salt_hex)
        return hmac.compare_digest(actual, stored)
    except Exception:
        return False


def create_session_token(username: str, display_name: str, role: str, phone: str = "") -> str:
    payload = {
        "u": username,
        "n": display_name,
        "r": role,
        "p": phone,
        "exp": int(time.time()) + SESSION_TTL_SEC,
    }
    b64 = base64.urlsafe_b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    sig = hmac.new(_get_secret(), b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def verify_session_token(token: str) -> Optional[Dict[str, Any]]:
    if not token or "." not in token:
        return None
    try:
        b64, sig = token.rsplit(".", 1)
        expected = hmac.new(_get_secret(), b64.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(b64.encode("ascii")).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return {
            "username": str(payload.get("u") or ""),
            "display_name": str(payload.get("n") or ""),
            "role": str(payload.get("r") or "user"),
            "phone": str(payload.get("p") or ""),
        }
    except Exception:
        return None


def parse_cookie_header(cookie_header: str, name: str = SESSION_COOKIE_NAME) -> str:
    for part in (cookie_header or "").split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip() == name:
                return v.strip()
    return ""


def register_user(display_name: str, username: str, phone: str, password: str) -> Dict[str, Any]:
    clean_name = (display_name or "").strip()[:80]
    clean_user = (username or "").strip().lower()[:100]
    clean_phone = normalize_phone(phone)

    if not clean_name:
        raise ValueError("Vui lòng nhập tên tài khoản / tên hiển thị.")
    if len(clean_user) < 3:
        raise ValueError("Tên đăng nhập phải từ 3 ký tự trở lên.")
    if not re.fullmatch(r"0\d{8,10}", clean_phone):
        raise ValueError("Vui lòng nhập số điện thoại hợp lệ (9–11 số, bắt đầu bằng 0).")
    if len(password or "") < 6:
        raise ValueError("Mật khẩu phải từ 6 ký tự trở lên.")

    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    with _LOCK:
        users = _load_users()
        if any((u.get("username") or "").lower() == clean_user for u in users):
            raise ValueError("Tên đăng nhập này đã có người sử dụng. Vui lòng chọn tên khác.")
        if any((u.get("display_name") or "").strip().lower() == clean_name.lower() for u in users):
            raise ValueError("Tên tài khoản này đã tồn tại (không được trùng tên). Vui lòng đặt tên khác.")
        if any(normalize_phone(u.get("phone") or "") == clean_phone for u in users):
            raise ValueError("Số điện thoại này đã được dùng để tạo 1 tài khoản. Mỗi SĐT chỉ tạo được 1 tài khoản.")

        # Admin is strictly the owner (Hà Thuỳ Dương: SĐT 0332125570 / email htd24307@gmail.com / hathuyduong2403)
        is_owner = (clean_phone in OWNER_PHONES) or (clean_user in OWNER_USERNAMES)
        role = "admin" if is_owner else "user"
        user_rec = {
            "username": clean_user,
            "display_name": clean_name,
            "phone": clean_phone,
            "role": role,
            "password_hash": hash_password(password),
            "created_at": now_iso,
            "last_login_at": now_iso,
        }
        users.append(user_rec)
        _save_users(users)
    return {"username": clean_user, "display_name": clean_name, "phone": clean_phone, "role": role}


def authenticate_user(identifier: str, password: str) -> Dict[str, Any]:
    clean_id = (identifier or "").strip().lower()
    clean_phone = normalize_phone(identifier)
    if not clean_id or not password:
        raise ValueError("Vui lòng nhập tên đăng nhập (hoặc SĐT) và mật khẩu.")
    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    with _LOCK:
        users = _load_users()
        for u in users:
            match_id = (u.get("username") or "").lower() == clean_id or (
                clean_phone and normalize_phone(u.get("phone") or "") == clean_phone
            )
            if match_id and verify_password(password, u.get("password_hash", "")):
                if u.get("is_locked"):
                    raise ValueError("Tài khoản của bạn đã bị Quản trị viên tạm khóa. Vui lòng liên hệ Admin (0332125570).")
                u["last_login_at"] = now_iso
                # Ensure owner phone/username always retains admin role
                if normalize_phone(u.get("phone") or "") in OWNER_PHONES or (u.get("username") or "").lower() in OWNER_USERNAMES:
                    u["role"] = "admin"
                _save_users(users)
                return {
                    "username": u["username"],
                    "display_name": u["display_name"],
                    "phone": u.get("phone", ""),
                    "role": u.get("role", "user"),
                }
    raise ValueError("Sai tên đăng nhập / SĐT hoặc mật khẩu.")


def request_password_reset_otp(phone: str) -> Dict[str, Any]:
    clean_phone = normalize_phone(phone)
    if not re.fullmatch(r"0\d{8,10}", clean_phone):
        raise ValueError("Vui lòng nhập số điện thoại hợp lệ.")
    with _LOCK:
        users = _load_users()
        target = next((u for u in users if normalize_phone(u.get("phone") or "") == clean_phone), None)
        if not target:
            raise ValueError("Không tìm thấy tài khoản nào đăng ký bằng số điện thoại này.")
        code = f"{secrets.randbelow(900000) + 100000}"
        _OTP_STORE[clean_phone] = {"code": code, "exp": time.time() + 300}
    print(f"[AUTH OTP] Mã khôi phục mật khẩu cho SĐT {clean_phone} ({target.get('username')}): {code}", flush=True)
    return {
        "ok": True,
        "phone": clean_phone,
        "username": target.get("username", ""),
        "demo_otp": code,
        "message": f"Đã gửi mã xác nhận OTP về SĐT {clean_phone} (hiệu lực 5 phút).",
    }


def reset_password_with_otp(phone: str, otp_code: str, new_password: str) -> Dict[str, Any]:
    clean_phone = normalize_phone(phone)
    code = (otp_code or "").strip()
    if len(new_password or "") < 6:
        raise ValueError("Mật khẩu mới phải từ 6 ký tự trở lên.")
    with _LOCK:
        entry = _OTP_STORE.get(clean_phone)
        if not entry or entry["exp"] < time.time():
            raise ValueError("Mã OTP đã hết hạn hoặc chưa được yêu cầu. Vui lòng bấm gửi lại mã.")
        if not hmac.compare_digest(entry["code"], code):
            raise ValueError("Mã OTP không chính xác.")
        users = _load_users()
        target = next((u for u in users if normalize_phone(u.get("phone") or "") == clean_phone), None)
        if not target:
            raise ValueError("Không tìm thấy tài khoản.")
        target["password_hash"] = hash_password(new_password)
        _save_users(users)
        _OTP_STORE.pop(clean_phone, None)
    return {"ok": True, "message": "Đổi mật khẩu thành công! Bạn có thể đăng nhập bằng mật khẩu mới."}


def log_analytics_event(
    event_type: str,
    path: str = "/",
    user_agent: str = "",
    ip: str = "",
    username: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    ua_l = (user_agent or "").lower()
    device = "Mobile" if any(k in ua_l for k in ("iphone", "android", "mobile", "ipad")) else "Desktop"
    visitor_hash = hashlib.sha256(f"{ip}|{user_agent}".encode("utf-8", errors="ignore")).hexdigest()[:12]
    rec: Dict[str, Any] = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "date": datetime.now().astimezone().strftime("%Y-%m-%d"),
        "type": event_type,
        "path": path,
        "device": device,
        "visitor": visitor_hash,
        "user": username or "guest",
    }
    if extra:
        rec["extra"] = extra
    with _LOCK:
        with ANALYTICS_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _read_all_events() -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if ANALYTICS_FILE.is_file():
        for ln in ANALYTICS_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not ln.strip():
                continue
            try:
                events.append(json.loads(ln))
            except Exception:
                pass
    return events


def get_user_personal_stats(username: str) -> Dict[str, Any]:
    """Return ONLY this user's own profile & activity stats (never other users' data)."""
    clean_user = (username or "").strip().lower()
    users = _load_users()
    me = next((u for u in users if (u.get("username") or "").lower() == clean_user), None)
    events = [e for e in _read_all_events() if (e.get("user") or "").lower() == clean_user]
    runs = [e for e in events if e.get("type") == "analysis_run"]
    chats = [e for e in events if e.get("type") == "chat_message"]
    visits = [e for e in events if e.get("type") == "page_view"]
    return {
        "profile": {
            "display_name": me.get("display_name", clean_user) if me else clean_user,
            "username": clean_user,
            "phone": me.get("phone", "") if me else "",
            "role": me.get("role", "user") if me else "user",
            "created_at": me.get("created_at", "") if me else "",
            "last_login_at": me.get("last_login_at", "") if me else "",
        },
        "summary": {
            "my_visits": len(visits),
            "my_analysis_runs": len(runs),
            "my_chat_messages": len(chats),
        },
        "recent_activity": events[-15:][::-1],
    }


def get_admin_dashboard_stats(contact_file: Path, audit_dir: Path) -> Dict[str, Any]:
    users = _load_users()
    events = _read_all_events()

    visits = [e for e in events if e.get("type") == "page_view"]
    runs = [e for e in events if e.get("type") == "analysis_run"]
    chats = [e for e in events if e.get("type") == "chat_message"]
    unique_visitors = len({e.get("visitor") for e in visits if e.get("visitor")})
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    visits_today = sum(1 for e in visits if e.get("date") == today)

    safe_users = []
    for u in users:
        uname = (u.get("username") or "").lower()
        u_runs = sum(1 for e in runs if (e.get("user") or "").lower() == uname)
        u_chats = sum(1 for e in chats if (e.get("user") or "").lower() == uname)
        safe_users.append(
            {
                "username": u.get("username", ""),
                "display_name": u.get("display_name", ""),
                "phone": u.get("phone", ""),
                "role": u.get("role", "user"),
                "is_locked": bool(u.get("is_locked", False)),
                "created_at": u.get("created_at", ""),
                "last_login_at": u.get("last_login_at", ""),
                "runs_count": u_runs,
                "chats_count": u_chats,
            }
        )

    device_counts = Counter(e.get("device", "Desktop") for e in visits)
    top_paths = [{"path": p, "count": c} for p, c in Counter(e.get("path", "/") for e in visits).most_common(6)]

    # 14-day daily time series for Admin Chart.js analytics
    now_dt = datetime.now().astimezone()
    days = [(now_dt - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(13, -1, -1)]
    visits_by_day = Counter(e.get("date") for e in visits)
    runs_by_day = Counter(e.get("date") for e in runs)
    chats_by_day = Counter(e.get("date") for e in chats)
    users_by_day = Counter((u.get("created_at") or "")[:10] for u in users)
    daily_series = [
        {
            "date": d,
            "label": d[5:],  # MM-DD
            "visits": visits_by_day.get(d, 0),
            "runs": runs_by_day.get(d, 0),
            "chats": chats_by_day.get(d, 0),
            "new_users": users_by_day.get(d, 0),
        }
        for d in days
    ]

    contacts: List[Dict[str, Any]] = []
    if contact_file.is_file():
        for ln in contact_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if ln.strip():
                try:
                    contacts.append(json.loads(ln))
                except Exception:
                    pass

    audit_count = len(list(audit_dir.glob("*.json"))) if audit_dir.is_dir() else 0

    return {
        "summary": {
            "total_visits": len(visits),
            "visits_today": visits_today,
            "unique_visitors": unique_visitors,
            "registered_users": len(safe_users),
            "analysis_runs": max(len(runs), audit_count),
            "chat_messages": len(chats),
            "contact_requests": len(contacts),
        },
        "daily_series": daily_series,
        "devices": dict(device_counts),
        "top_paths": top_paths,
        "users": safe_users,
        "recent_contacts": contacts[-10:][::-1],
        "recent_activity": events[-20:][::-1],
    }


def toggle_user_lock(username: str, locked: bool) -> Dict[str, Any]:
    clean_u = (username or "").strip().lower()
    if not clean_u:
        raise ValueError("Thiếu tên tài khoản.")
    with _LOCK:
        users = _load_users()
        target = next((u for u in users if (u.get("username") or "").lower() == clean_u), None)
        if not target:
            raise ValueError("Không tìm thấy tài khoản.")
        if target.get("role") == "admin" or normalize_phone(target.get("phone") or "") in OWNER_PHONES:
            raise ValueError("Không thể khóa tài khoản Quản trị viên chủ sở hữu.")
        target["is_locked"] = bool(locked)
        _save_users(users)
    return {"ok": True, "username": clean_u, "is_locked": bool(locked)}


DEFAULT_SITE_SETTINGS: Dict[str, Any] = {
    "site_title": "Hà Thuỳ Dương · Data Analyst & Business Intelligence",
    "announcement_bar": "",
    "maintenance_mode": False,
}


def get_site_settings() -> Dict[str, Any]:
    if not SETTINGS_FILE.is_file():
        return dict(DEFAULT_SITE_SETTINGS)
    try:
        raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        out = dict(DEFAULT_SITE_SETTINGS)
        if isinstance(raw, dict):
            out.update(raw)
        return out
    except Exception:
        return dict(DEFAULT_SITE_SETTINGS)


def update_site_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    with _LOCK:
        cur = get_site_settings()
        if "site_title" in updates and str(updates["site_title"]).strip():
            cur["site_title"] = str(updates["site_title"]).strip()[:120]
        if "announcement_bar" in updates:
            cur["announcement_bar"] = str(updates["announcement_bar"]).strip()[:240]
        if "maintenance_mode" in updates:
            cur["maintenance_mode"] = bool(updates["maintenance_mode"])
        SETTINGS_FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        return cur
