#!/usr/bin/env python3
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import traceback
from threading import Thread
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def parse_int_set(raw: str):
    out = set()
    for item in (raw or "").split(","):
        s = item.strip()
        if not s:
            continue
        try:
            out.add(int(s))
        except ValueError:
            pass
    return out


def parse_str_set(raw: str):
    out = set()
    for item in (raw or "").split(","):
        s = item.strip().lstrip("@").lower()
        if s:
            out.add(s)
    return out


TOKEN = os.environ.get("BOT_TOKEN", "").strip()
BASE_URL = os.environ.get("BASE_URL", "https://example.com:8443").rstrip("/")
SUPPORT_TEXT = os.environ.get("SUPPORT_TEXT", "Поддержка: @admin")
SUPPORT_CHAT_URL = os.environ.get("SUPPORT_CHAT_URL", "https://t.me/admin")
FREE_DAYS = int(os.environ.get("FREE_DAYS", "1"))
START_RATE_LIMIT_SEC = int(os.environ.get("START_RATE_LIMIT_SEC", "30"))
DB_PATH = os.environ.get("DB_PATH", "/var/lib/hexenvpn-bot/bot.db")
CLIENTS_JSON = os.environ.get("CLIENTS_JSON", "/var/lib/vless-sub/clients.json")
ADD_USER_CMD = os.environ.get("ADD_USER_CMD", "/usr/local/sbin/vless-add-user")
DEL_USER_CMD = os.environ.get("DEL_USER_CMD", "/usr/local/sbin/vless-del-user")
SYNC_EXPIRE_CMD = os.environ.get("SYNC_EXPIRE_CMD", "/usr/local/sbin/vless-sync-expire")
SYNC_GRACE_DAYS = int(os.environ.get("SYNC_GRACE_DAYS", "1"))
MONITOR_ENABLED = os.environ.get("MONITOR_ENABLED", "1").strip() == "1"
MONITOR_INTERVAL_SEC = int(os.environ.get("MONITOR_INTERVAL_SEC", "300"))
MONITOR_COOLDOWN_SEC = int(os.environ.get("MONITOR_COOLDOWN_SEC", "1800"))
MONITOR_CMD = os.environ.get("MONITOR_CMD", "/usr/local/sbin/healthcheck-master-replicas")
MONITOR_CHECK_USER = os.environ.get("MONITOR_CHECK_USER", "").strip()
METRICS_CMD = os.environ.get("METRICS_CMD", "/usr/local/sbin/metrics-master-light")
ADMIN_TG_IDS = parse_int_set(os.environ.get("ADMIN_TG_IDS", ""))
ADMIN_TG_USERNAMES = parse_str_set(os.environ.get("ADMIN_TG_USERNAMES", ""))
PRIMARY_ADMIN_TG_ID = int(os.environ.get("PRIMARY_ADMIN_TG_ID", "227380225"))

if not TOKEN:
    print("BOT_TOKEN is empty", file=sys.stderr)
    sys.exit(1)

API_BASE = f"https://api.telegram.org/bot{TOKEN}"

CB_MAIN = "main"
CB_MY_SUB = "my_sub"
CB_PAY = "pay"
CB_PAY_TARIFF_1 = "pay_tariff_1"
CB_PAY_TARIFF_3 = "pay_tariff_3"
CB_PAY_TARIFF_6 = "pay_tariff_6"
CB_PAY_TARIFF_12 = "pay_tariff_12"
CB_PAY_INVOICE_1 = "pay_invoice_1"
CB_PAY_INVOICE_3 = "pay_invoice_3"
CB_PAY_INVOICE_6 = "pay_invoice_6"
CB_PAY_INVOICE_12 = "pay_invoice_12"
CB_PAY_BACK = "pay_back"
CB_SUPPORT = "support"
CB_ADMIN = "admin"
CB_ADMIN_ADD = "admin_add"
CB_ADMIN_EDIT = "admin_edit"
CB_ADMIN_BLOCK = "admin_block"
CB_ADMIN_UNBLOCK = "admin_unblock"
CB_ADMIN_TRIAL_OFF = "admin_trial_off"
CB_ADMIN_DEL = "admin_del"
CB_ADMIN_LIST = "admin_list"
CB_ADMIN_FIND = "admin_find"
CB_ADMIN_STATUS = "admin_status"
CB_ADMIN_USERS = "admin_users"
CB_ADMIN_ACCESS = "admin_access"
CB_ADMIN_SERVICE = "admin_service"
CB_ADMIN_CANCEL = "admin_cancel"
CB_CONFIRM_BLOCK = "confirm_block"
CB_CONFIRM_UNBLOCK = "confirm_unblock"
CB_CONFIRM_TRIAL_OFF = "confirm_trial_off"
CB_CONFIRM_DELETE = "confirm_delete"
CB_SEL_PREV = "sel_prev"
CB_SEL_NEXT = "sel_next"
CB_SEL_FIND = "sel_find"
CB_SEL_USER_PREFIX = "sel_user:"

STATE_ADD_NAME = "add_name"
STATE_ADD_DAYS = "add_days"
STATE_EDIT_DAYS = "edit_days"
STATE_BLOCK_CONFIRM = "block_confirm"
STATE_UNBLOCK_CONFIRM = "unblock_confirm"
STATE_TRIAL_OFF_CONFIRM = "trial_off_confirm"
STATE_DEL_CONFIRM = "del_confirm"
STATE_SELECT_USER = "select_user"
STATE_SEARCH_QUERY = "search_query"

SELECT_PAGE_SIZE = 8
JOB_PENDING = "pending"
JOB_RUNNING = "running"
JOB_DONE = "done"
JOB_FAILED = "failed"

PAYMENT_PLANS = {
    1: {"months": 1, "rub": 200, "stars": 250, "days": 30},
    3: {"months": 3, "rub": 500, "stars": 550, "days": 90},
    6: {"months": 6, "rub": 900, "stars": 950, "days": 180},
    12: {"months": 12, "rub": 1700, "stars": 1750, "days": 365},
}


def api_call(method: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/{method}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=35) as resp:
        obj = json.loads(resp.read().decode("utf-8", errors="ignore"))
    if not obj.get("ok"):
        raise RuntimeError(f"Telegram API {method} failed: {obj}")
    return obj.get("result")


def init_db(conn: sqlite3.Connection):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tg_users (
            tg_id INTEGER PRIMARY KEY,
            username TEXT,
            vpn_name TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            last_start_at INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_state (
            tg_id INTEGER PRIMARY KEY,
            step TEXT NOT NULL,
            payload TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS provisioning_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            username TEXT,
            vpn_name TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            started_at INTEGER NOT NULL DEFAULT 0,
            finished_at INTEGER NOT NULL DEFAULT 0,
            result_text TEXT NOT NULL DEFAULT ""
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trial_notices (
            tg_id INTEGER NOT NULL,
            notice_kind TEXT NOT NULL,
            expire_ts INTEGER NOT NULL,
            sent_at INTEGER NOT NULL,
            PRIMARY KEY (tg_id, notice_kind, expire_ts)
        )
        """
    )
    conn.commit()


def get_user(conn: sqlite3.Connection, tg_id: int):
    cur = conn.execute(
        "SELECT tg_id, username, vpn_name, created_at, last_start_at FROM tg_users WHERE tg_id=?",
        (tg_id,),
    )
    return cur.fetchone()


def delete_tg_users_by_vpn_name(conn: sqlite3.Connection, vpn_name: str):
    conn.execute("DELETE FROM tg_users WHERE vpn_name=?", (vpn_name,))
    conn.commit()


def tg_ids_by_vpn_name(conn: sqlite3.Connection, vpn_name: str):
    cur = conn.execute("SELECT tg_id FROM tg_users WHERE vpn_name=?", (vpn_name,))
    return [int(r[0]) for r in cur.fetchall() if r and r[0]]


def notify_user_change(conn: sqlite3.Connection, vpn_name: str, text: str):
    ids = tg_ids_by_vpn_name(conn, vpn_name)
    for tg_id in ids:
        try:
            send_message(int(tg_id), text[:3500], kb_main(is_admin=False))
        except Exception as e:
            print(f"[notify-user-change-error] vpn={vpn_name} tg_id={tg_id} err={e}", file=sys.stderr, flush=True)


def upsert_user(conn: sqlite3.Connection, tg_id: int, username: str, vpn_name: str):
    now = int(time.time())
    conn.execute(
        """
        INSERT INTO tg_users (tg_id, username, vpn_name, created_at, last_start_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(tg_id) DO UPDATE SET
          username=excluded.username,
          vpn_name=excluded.vpn_name,
          last_start_at=excluded.last_start_at
        """,
        (tg_id, username, vpn_name, now, now),
    )
    conn.commit()


def touch_start(conn: sqlite3.Connection, tg_id: int):
    now = int(time.time())
    conn.execute("UPDATE tg_users SET last_start_at=? WHERE tg_id=?", (now, tg_id))
    conn.commit()


def get_admin_state(conn: sqlite3.Connection, tg_id: int):
    cur = conn.execute("SELECT step, payload FROM admin_state WHERE tg_id=?", (tg_id,))
    row = cur.fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row[1])
    except Exception:
        payload = {}
    return {"step": row[0], "payload": payload}


def set_admin_state(conn: sqlite3.Connection, tg_id: int, step: str, payload: dict | None = None):
    if payload is None:
        payload = {}
    now = int(time.time())
    conn.execute(
        """
        INSERT INTO admin_state (tg_id, step, payload, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(tg_id) DO UPDATE SET step=excluded.step, payload=excluded.payload, updated_at=excluded.updated_at
        """,
        (tg_id, step, json.dumps(payload, ensure_ascii=False), now),
    )
    conn.commit()


def clear_admin_state(conn: sqlite3.Connection, tg_id: int):
    conn.execute("DELETE FROM admin_state WHERE tg_id=?", (tg_id,))
    conn.commit()


def get_pending_provision_job(conn: sqlite3.Connection, tg_id: int):
    cur = conn.execute(
        "SELECT id, status, created_at, vpn_name FROM provisioning_jobs WHERE tg_id=? AND status IN (?, ?) ORDER BY id DESC LIMIT 1",
        (tg_id, JOB_PENDING, JOB_RUNNING),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {"id": int(row[0]), "status": row[1], "created_at": int(row[2] or 0), "vpn_name": row[3]}


def enqueue_provision_job(conn: sqlite3.Connection, tg_id: int, chat_id: int, username: str, vpn_name: str):
    now = int(time.time())
    conn.execute(
        "INSERT INTO provisioning_jobs (tg_id, chat_id, username, vpn_name, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (tg_id, chat_id, username, vpn_name, JOB_PENDING, now),
    )
    conn.commit()


def claim_next_provision_job(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    cur.execute(
        "SELECT id, tg_id, chat_id, username, vpn_name FROM provisioning_jobs WHERE status=? ORDER BY id ASC LIMIT 1",
        (JOB_PENDING,),
    )
    row = cur.fetchone()
    if not row:
        conn.commit()
        return None

    jid = int(row[0])
    now = int(time.time())
    cur.execute("UPDATE provisioning_jobs SET status=?, started_at=? WHERE id=?", (JOB_RUNNING, now, jid))
    conn.commit()
    return {
        "id": jid,
        "tg_id": int(row[1]),
        "chat_id": int(row[2]),
        "username": (row[3] or ""),
        "vpn_name": row[4],
    }


def finish_provision_job(conn: sqlite3.Connection, job_id: int, ok: bool, result_text: str):
    now = int(time.time())
    status = JOB_DONE if ok else JOB_FAILED
    conn.execute(
        "UPDATE provisioning_jobs SET status=?, finished_at=?, result_text=? WHERE id=?",
        (status, now, (result_text or "")[:4000], job_id),
    )
    conn.commit()


def provision_worker_loop():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    while True:
        try:
            job = claim_next_provision_job(conn)
            if not job:
                time.sleep(1)
                continue

            ok, out = provision_user(job["vpn_name"])
            if ok:
                existing = get_user(conn, int(job["tg_id"]))
                upsert_user(conn, int(job["tg_id"]), job.get("username", ""), job["vpn_name"])
                set_trial_flag(job["vpn_name"], True)
                finish_provision_job(conn, int(job["id"]), True, out)
                if existing is None:
                    uname = (job.get("username") or "").strip()
                    who = f"@{uname}" if uname else f"tg_id={int(job['tg_id'])}"
                    send_admin_alert(
                        "🆕 Новый пользователь зарегистрирован.\n"
                        f"Пользователь: {who}\n"
                        f"VPN: {job['vpn_name']}\n"
                        f"Триал: {FREE_DAYS} дн."
                    )
                send_message(
                    int(job["chat_id"]),
                    f"✅ Подписка готова.\n🧪 Пробный доступ: {FREE_DAYS} дн.\n"
                    "Открой «👤 Моя подписка», чтобы подключиться.\n"
                    "Для продления используй «💰 Оплатить подписку».",
                    kb_main(is_admin=False),
                )
            else:
                finish_provision_job(conn, int(job["id"]), False, out)
                send_message(
                    int(job["chat_id"]),
                    "❌ Не удалось создать подписку автоматически. Напиши в поддержку.\n\n" + SUPPORT_TEXT,
                    kb_main(is_admin=False),
                )
                uname = (job.get("username") or "").strip()
                who = f"@{uname}" if uname else f"tg_id={int(job['tg_id'])}"
                send_admin_alert(
                    "🚨 Ошибка регистрации нового пользователя.\n"
                    f"Пользователь: {who}\n"
                    f"VPN: {job['vpn_name']}\n\n"
                    f"{(out or '').strip()[:1200]}"
                )
                print(f"provision failed for {job['vpn_name']}:\n{out}", file=sys.stderr)

        except Exception as e:
            print(f"worker error: {e}", file=sys.stderr)
            traceback.print_exc()
            time.sleep(2)


def is_admin_user(user_obj: dict):
    tg_id = int(user_obj.get("id") or 0)
    if tg_id == PRIMARY_ADMIN_TG_ID:
        return True
    username = (user_obj.get("username") or "").strip().lstrip("@").lower()
    if tg_id in ADMIN_TG_IDS:
        return True
    if username and username in ADMIN_TG_USERNAMES:
        return True
    return False


def safe_tg_name(user_obj: dict):
    username = (user_obj.get("username") or "").strip()
    if username:
        return f"@{username}"
    fn = (user_obj.get("first_name") or "").strip()
    ln = (user_obj.get("last_name") or "").strip()
    full = (fn + " " + ln).strip()
    return full or str(user_obj.get("id"))


def run_cmd(args: list[str], timeout_sec: int = 240):
    started = time.time()
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout_sec)
        rc = int(proc.returncode)
        out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        rc = 124
        out = f"timeout after {timeout_sec}s"
    if rc != 0:
        cmd = " ".join(args)
        print(
            f"[cmd-error] rc={rc} sec={time.time()-started:.2f} cmd={cmd}\n{out[:1200]}",
            file=sys.stderr,
            flush=True,
        )
    return rc, out


def admin_chat_ids():
    ids = set(ADMIN_TG_IDS)
    ids.add(PRIMARY_ADMIN_TG_ID)
    return sorted(x for x in ids if x > 0)


def send_admin_alert(text: str):
    for chat_id in admin_chat_ids():
        try:
            send_message(chat_id, text[:3500], kb_main(is_admin=True))
        except Exception as e:
            print(f"[monitor-alert-send-error] chat_id={chat_id} err={e}", file=sys.stderr, flush=True)


def trial_notice_already_sent(conn: sqlite3.Connection, tg_id: int, notice_kind: str, expire_ts: int):
    cur = conn.execute(
        "SELECT 1 FROM trial_notices WHERE tg_id=? AND notice_kind=? AND expire_ts=? LIMIT 1",
        (tg_id, notice_kind, int(expire_ts)),
    )
    return cur.fetchone() is not None


def mark_trial_notice_sent(conn: sqlite3.Connection, tg_id: int, notice_kind: str, expire_ts: int):
    now = int(time.time())
    conn.execute(
        """
        INSERT OR IGNORE INTO trial_notices (tg_id, notice_kind, expire_ts, sent_at)
        VALUES (?, ?, ?, ?)
        """,
        (int(tg_id), notice_kind, int(expire_ts), now),
    )
    conn.commit()


def answer_pre_checkout(pre_checkout_query_id: str, ok: bool, error_message: str = ""):
    payload = {"pre_checkout_query_id": pre_checkout_query_id, "ok": bool(ok)}
    if not ok and error_message:
        payload["error_message"] = error_message[:180]
    api_call("answerPreCheckoutQuery", payload)


def send_stars_invoice(chat_id: int, months: int):
    plan = PAYMENT_PLANS.get(months)
    if not plan:
        raise RuntimeError(f"Unknown payment plan: {months}")
    stars = int(plan["stars"])
    title = f"Подписка на {months} мес."
    if months == 1:
        desc = "Оплата подписки на 1 месяц"
    elif months in (3, 6):
        desc = f"Оплата подписки на {months} месяца"
    else:
        desc = f"Оплата подписки на {months} месяцев"
    payload = {
        "chat_id": int(chat_id),
        "title": title,
        "description": desc,
        "payload": f"sub_{months}m",
        "currency": "XTR",
        "prices": [{"label": title, "amount": stars}],
    }
    api_call("sendInvoice", payload)


def monitor_loop():
    if not MONITOR_ENABLED:
        print("[monitor] disabled", file=sys.stderr, flush=True)
        return

    last_bad_at = 0
    last_bad_sig = ""
    was_bad = False
    print(
        f"[monitor] enabled interval={MONITOR_INTERVAL_SEC}s cooldown={MONITOR_COOLDOWN_SEC}s cmd={MONITOR_CMD}",
        file=sys.stderr,
        flush=True,
    )

    while True:
        try:
            args = [MONITOR_CMD]
            if MONITOR_CHECK_USER:
                args += ["--user", MONITOR_CHECK_USER]
            rc, out = run_cmd(args, timeout_sec=max(60, min(MONITOR_INTERVAL_SEC, 180)))
            now = int(time.time())
            sig = f"{rc}:{(out or '')[:300]}"

            if rc == 0:
                if was_bad:
                    send_admin_alert("✅ Мониторинг: восстановлено. Healthcheck снова OK.")
                    print("[monitor] recovered", file=sys.stderr, flush=True)
                was_bad = False
            else:
                need_alert = (not was_bad) or (sig != last_bad_sig and (now - last_bad_at) >= MONITOR_COOLDOWN_SEC)
                if need_alert:
                    msg = "🚨 Мониторинг: проблема на VPN-узлах.\n\n" + (out[:2500] if out else f"rc={rc}")
                    send_admin_alert(msg)
                    last_bad_at = now
                    last_bad_sig = sig
                    print("[monitor] alerted", file=sys.stderr, flush=True)
                was_bad = True
        except Exception as e:
            print(f"[monitor-loop-error] {e}", file=sys.stderr, flush=True)
            traceback.print_exc()

        time.sleep(max(30, MONITOR_INTERVAL_SEC))


def trial_notice_loop():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    while True:
        try:
            now = int(time.time())
            # Build quick map by vpn_name.
            by_name = {}
            for c in load_clients():
                nm = (c.get("name") or "").strip()
                if nm:
                    by_name[nm] = c

            cur = conn.execute("SELECT tg_id, vpn_name FROM tg_users")
            rows = cur.fetchall()
            for tg_id, vpn_name in rows:
                row = by_name.get(vpn_name or "")
                if not row:
                    continue
                if not bool(row.get("trial", False)):
                    continue

                exp = int(row.get("expire") or 0)
                if exp <= 0:
                    continue
                left = exp - now

                if 0 < left <= 6 * 3600:
                    kind = "trial_6h"
                    if not trial_notice_already_sent(conn, int(tg_id), kind, exp):
                        send_message(
                            int(tg_id),
                            "⏰ Пробный доступ скоро завершится (меньше 6 часов).\n"
                            "Чтобы продолжить пользоваться VPN без перерыва, продлите подписку.",
                            kb_pay(),
                        )
                        mark_trial_notice_sent(conn, int(tg_id), kind, exp)
                elif left <= 0:
                    kind = "trial_expired"
                    if not trial_notice_already_sent(conn, int(tg_id), kind, exp):
                        send_message(
                            int(tg_id),
                            "⛔ Пробный доступ завершен.\n"
                            "Чтобы восстановить доступ, оплатите подписку.",
                            kb_pay(),
                        )
                        mark_trial_notice_sent(conn, int(tg_id), kind, exp)
        except Exception as e:
            print(f"[trial-notice-loop-error] {e}", file=sys.stderr, flush=True)
            traceback.print_exc()

        time.sleep(300)


def load_clients():
    p = Path(CLIENTS_JSON)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_clients(clients: list[dict]):
    p = Path(CLIENTS_JSON)
    bak = p.with_name(p.name + ".bot.bak")
    if p.exists():
        bak.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    p.write_text(json.dumps(clients, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_client_by_name(name: str):
    for c in load_clients():
        if (c.get("name") or "") == name:
            return c
    return None


def set_trial_flag(name: str, is_trial: bool):
    clients = load_clients()
    changed = False
    for c in clients:
        if (c.get("name") or "") == name:
            c["trial"] = bool(is_trial)
            changed = True
            break
    if changed:
        save_clients(clients)
    return changed


def set_user_trial(name: str, is_trial: bool):
    changed = set_trial_flag(name, is_trial)
    if not changed:
        return False, "Пользователь не найден"
    return True, "OK"


def master_has_vpn_user(name: str):
    return get_client_by_name(name) is not None


def provision_user(name: str):
    rc, out = run_cmd([ADD_USER_CMD, "--name", name, "--days", str(FREE_DAYS)], timeout_sec=300)
    if rc == 0:
        return True, out
    lowered = out.lower()
    if "already exists" in lowered and master_has_vpn_user(name):
        return True, out
    return False, out


def sync_expire_apply():
    return run_cmd([SYNC_EXPIRE_CMD, "--apply", "--grace-days", str(SYNC_GRACE_DAYS)], timeout_sec=120)


def set_user_expire_days(name: str, days: int):
    clients = load_clients()
    found = False
    now_ts = int(time.time())
    new_exp = now_ts + days * 86400
    for c in clients:
        if (c.get("name") or "") == name:
            c["expire"] = int(new_exp)
            c["revoked"] = False
            found = True
            break
    if not found:
        return False, "Пользователь не найден"
    save_clients(clients)
    rc, out = sync_expire_apply()
    if rc != 0:
        return False, f"Срок обновлен, но sync завершился с ошибкой:\n{out}"
    return True, "OK"


def extend_user_expire_days(name: str, days: int):
    clients = load_clients()
    found = False
    now_ts = int(time.time())
    for c in clients:
        if (c.get("name") or "") == name:
            cur_exp = int(c.get("expire") or 0)
            base = max(now_ts, cur_exp)
            c["expire"] = int(base + days * 86400)
            c["revoked"] = False
            found = True
            break
    if not found:
        return False, "Пользователь не найден"
    save_clients(clients)
    rc, out = sync_expire_apply()
    if rc != 0:
        return False, f"Срок продлен, но sync завершился с ошибкой:\n{out}"
    return True, "OK"


def set_user_blocked(name: str, blocked: bool = True):
    clients = load_clients()
    found = False
    for c in clients:
        if (c.get("name") or "") == name:
            c["revoked"] = bool(blocked)
            found = True
            break
    if not found:
        return False, "Пользователь не найден"
    save_clients(clients)
    rc, out = sync_expire_apply()
    if rc != 0:
        return False, f"Статус изменен, но sync завершился с ошибкой:\n{out}"
    return True, "OK"


def find_subscription_info(vpn_name: str):
    row = get_client_by_name(vpn_name)
    if not row:
        return None
    exp = int(row.get("expire") or 0)
    exp_txt = "не задана"
    if exp > 0:
        dt = datetime.fromtimestamp(exp, tz=timezone.utc).astimezone()
        exp_txt = dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    return {
        "expire_text": exp_txt,
        "expire_ts": exp,
        "trial": bool(row.get("trial", False)),
        "menu_url": f"{BASE_URL}/i/{vpn_name}",
    }


def count_clients():
    return len(load_clients())


def tg_username_map(conn: sqlite3.Connection):
    m = {}
    cur = conn.execute("SELECT vpn_name, username FROM tg_users")
    for vpn_name, username in cur.fetchall():
        if vpn_name and username:
            m[vpn_name] = username
    return m


def display_name_for(conn: sqlite3.Connection, vpn_name: str):
    if vpn_name.startswith("tg_"):
        m = tg_username_map(conn)
        u = (m.get(vpn_name) or "").strip().lstrip("@")
        if u:
            return f"@{u}"
    return vpn_name


def is_valid_name(name: str):
    return bool(re.fullmatch(r"[A-Za-z0-9._-]+", name or ""))


def parse_positive_int(text: str):
    text = (text or "").strip()
    if not text.isdigit():
        return None
    n = int(text)
    if n <= 0:
        return None
    return n


def build_user_rows(conn: sqlite3.Connection, query: str = "", filter_mode: str = "all"):
    rows = []
    q = (query or "").strip().lower()
    for c in load_clients():
        name = (c.get("name") or "").strip()
        if not name:
            continue
        exp = int(c.get("expire") or 0)
        revoked = bool(c.get("revoked") or False)
        is_trial = bool(c.get("trial", False))
        if filter_mode == "only_blocked" and not revoked:
            continue
        if filter_mode == "only_active" and revoked:
            continue
        if filter_mode == "only_trial" and not is_trial:
            continue
        disp = display_name_for(conn, name)
        searchable = f"{name} {disp}".lower()
        if q and q not in searchable:
            continue
        if revoked:
            status = "⛔"
        elif exp > 0 and int(time.time()) > exp:
            status = "⌛"
        elif is_trial:
            status = "🧪"
        else:
            status = "✅"
        exp_txt = "-"
        if exp > 0:
            exp_txt = datetime.fromtimestamp(exp, tz=timezone.utc).astimezone().strftime("%d.%m.%Y")
        rows.append({"name": name, "display": disp, "exp_txt": exp_txt, "status": status})
    rows.sort(key=lambda x: x["display"].lower())
    return rows


def kb_main(is_admin: bool):
    rows = [
        [{"text": "👤 Моя подписка", "callback_data": CB_MY_SUB}],
        [{"text": "💰 Оплатить подписку", "callback_data": CB_PAY}],
        [{"text": "❓ Поддержка", "callback_data": CB_SUPPORT}],
    ]
    if is_admin:
        rows.append([{"text": "🛠 Админка", "callback_data": CB_ADMIN}])
    return {"inline_keyboard": rows}


def kb_my_sub(connect_url: str):
    return {
        "inline_keyboard": [
            [{"text": "🔌 Подключиться", "url": connect_url}],
            [{"text": "⬅️ Вернуться назад", "callback_data": CB_MAIN}],
        ]
    }


def kb_pay():
    return {
        "inline_keyboard": [
            [{"text": "1 мес • 200₽", "callback_data": CB_PAY_TARIFF_1}],
            [{"text": "3 мес • 500₽", "callback_data": CB_PAY_TARIFF_3}],
            [{"text": "6 мес • 900₽", "callback_data": CB_PAY_TARIFF_6}],
            [{"text": "12 мес • 1700₽", "callback_data": CB_PAY_TARIFF_12}],
            [{"text": "⬅️ Вернуться назад", "callback_data": CB_MAIN}],
        ]
    }


def kb_pay_plan(months: int, stars: int):
    cb = {
        1: CB_PAY_INVOICE_1,
        3: CB_PAY_INVOICE_3,
        6: CB_PAY_INVOICE_6,
        12: CB_PAY_INVOICE_12,
    }.get(months, CB_PAY)
    return {
        "inline_keyboard": [
            [{"text": f"⭐ Оплатить {stars}", "callback_data": cb}],
            [{"text": "⬅️ К тарифам", "callback_data": CB_PAY_BACK}],
        ]
    }


def kb_support():
    return {
        "inline_keyboard": [
            [{"text": "💬 Открыть чат с админом", "url": SUPPORT_CHAT_URL}],
        ]
    }


def kb_admin():
    return {
        "inline_keyboard": [
            [
                {"text": "👥 Пользователи", "callback_data": CB_ADMIN_USERS},
                {"text": "🔐 Доступ", "callback_data": CB_ADMIN_ACCESS},
            ],
            [{"text": "🖥 Сервис", "callback_data": CB_ADMIN_SERVICE}],
            [{"text": "⬅️ Вернуться назад", "callback_data": CB_MAIN}],
        ]
    }


def kb_admin_users():
    return {
        "inline_keyboard": [
            [
                {"text": "📋 Список", "callback_data": CB_ADMIN_LIST},
                {"text": "🔎 Поиск", "callback_data": CB_ADMIN_FIND},
            ],
            [
                {"text": "➕ Добавить", "callback_data": CB_ADMIN_ADD},
                {"text": "🗑 Удалить", "callback_data": CB_ADMIN_DEL},
            ],
            [{"text": "⬅️ Вернуться назад", "callback_data": CB_ADMIN}],
        ]
    }


def kb_admin_access():
    return {
        "inline_keyboard": [
            [
                {"text": "🗓 Срок", "callback_data": CB_ADMIN_EDIT},
                {"text": "⛔ Блок", "callback_data": CB_ADMIN_BLOCK},
            ],
            [
                {"text": "🔓 Разблок", "callback_data": CB_ADMIN_UNBLOCK},
                {"text": "🏷 Снять триал", "callback_data": CB_ADMIN_TRIAL_OFF},
            ],
            [{"text": "⬅️ Вернуться назад", "callback_data": CB_ADMIN}],
        ]
    }


def kb_admin_service():
    return {
        "inline_keyboard": [
            [{"text": "📊 Состояние узла", "callback_data": CB_ADMIN_STATUS}],
            [{"text": "⬅️ Вернуться назад", "callback_data": CB_ADMIN}],
        ]
    }


def kb_admin_back():
    return {
        "inline_keyboard": [
            [{"text": "⬅️ Вернуться назад", "callback_data": CB_ADMIN}],
            [{"text": "❌ Отмена", "callback_data": CB_ADMIN_CANCEL}],
        ]
    }


def kb_confirm(action_cb: str):
    return {
        "inline_keyboard": [
            [{"text": "✅ Подтвердить", "callback_data": action_cb}],
            [{"text": "❌ Отмена", "callback_data": CB_ADMIN_CANCEL}],
        ]
    }


def kb_selector(rows: list[dict], offset: int, total: int, can_choose: bool):
    buttons = []
    if can_choose:
        for r in rows:
            label = f"{r['status']} {r['display']} | {r['exp_txt']}"
            buttons.append([{"text": label[:60], "callback_data": f"{CB_SEL_USER_PREFIX}{r['name']}"}])
    nav = []
    if offset > 0:
        nav.append({"text": "⬅️", "callback_data": CB_SEL_PREV})
    if offset + len(rows) < total:
        nav.append({"text": "➡️", "callback_data": CB_SEL_NEXT})
    if nav:
        buttons.append(nav)
    buttons.append([{"text": "🔎 Поиск", "callback_data": CB_SEL_FIND}])
    buttons.append([{"text": "⬅️ Вернуться назад", "callback_data": CB_ADMIN}])
    return {"inline_keyboard": buttons}


def send_message(chat_id: int, text: str, reply_markup: dict, parse_mode: str | None = None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": reply_markup,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    api_call("sendMessage", payload)


def answer_callback(callback_query_id: str, text: str = ""):
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    api_call("answerCallbackQuery", payload)


def ensure_bot_menu_commands():
    api_call(
        "setMyCommands",
        {
            "commands": [
                {"command": "start", "description": "Начать работу с ботом"},
            ]
        },
    )


def show_main(chat_id: int, user_obj: dict):
    admin = is_admin_user(user_obj)
    tg_name = safe_tg_name(user_obj)
    text = (
        f"Привет, {tg_name}!\n"
        "Добро пожаловать в HexenKVN.\n\n"
        "Рекомендую начать с пункта «Моя подписка»:\n"
        "там срок действия и ссылка для подключения.\n\n"
        "Выберите действие:"
    )
    send_message(chat_id, text, kb_main(is_admin=admin))


def show_my_subscription(conn: sqlite3.Connection, msg: dict):
    user = msg["from"]
    chat_id = msg["chat"]["id"]
    tg_id = int(user["id"])

    row = get_user(conn, tg_id)
    if not row:
        send_message(chat_id, "Подписка не найдена. Нажми /start", kb_main(is_admin=is_admin_user(user)))
        return

    vpn_name = row[2]
    info = find_subscription_info(vpn_name)
    if not info:
        send_message(chat_id, "Не нашел подписку в системе. Напиши в поддержку.\n\n" + SUPPORT_TEXT, kb_main(is_admin=is_admin_user(user)))
        return

    expire_ts = int(info.get("expire_ts") or 0)
    is_trial = bool(info.get("trial", False))
    now_ts = int(time.time())
    if expire_ts > 0:
        dt = datetime.fromtimestamp(expire_ts, tz=timezone.utc).astimezone()
        date_text = dt.strftime("%d.%m.%Y")
        days_left = int((expire_ts - now_ts + 86399) / 86400)
        if days_left < 0:
            days_left = 0
        valid_line = f"<b>Действует до - {date_text} ({days_left} дн.)</b>"
    else:
        valid_line = "<b>Действует до - не задано</b>"

    if is_trial:
        if expire_ts > now_ts:
            text = (
                "🧪 Статус подписки - <b>Пробный доступ</b>\n"
                f"{valid_line}\n\n"
                "Чтобы продолжить пользоваться VPN после пробного периода, продлите подписку через «💰 Оплатить подписку».\n\n"
                "ℹ️ Если кнопка «Подключиться» не работает, открой ссылку:\n"
                f"{info['menu_url']}"
            )
        else:
            text = (
                "⛔ Статус подписки - <b>Пробный доступ завершен</b>\n"
                f"{valid_line}\n\n"
                "Для восстановления доступа оплатите подписку в разделе «💰 Оплатить подписку»."
            )
    else:
        text = (
            "✅ Статус подписки - <b>Активна</b>\n"
            f"{valid_line}\n\n"
            "ℹ️ Если кнопка «Подключиться» не работает, то перейдите по ссылке:\n"
            f"{info['menu_url']}"
        )
    send_message(chat_id, text, kb_my_sub(info["menu_url"]), parse_mode="HTML")


def show_pay(msg: dict):
    text = (
        "Выберите тариф:"
    )
    send_message(msg["chat"]["id"], text, kb_pay())


def show_pay_plan(msg: dict, months: int):
    chat_id = msg["chat"]["id"]
    plan = PAYMENT_PLANS.get(months)
    if not plan:
        send_message(chat_id, "Неизвестный тариф.", kb_pay())
        return
    stars = int(plan["stars"])
    text = f"Оплата подписки на {months} мес.\n{stars} ⭐"
    send_message(chat_id, text, kb_pay_plan(months, stars))


def start_stars_payment(msg: dict, months: int):
    chat_id = int(msg["chat"]["id"])
    try:
        send_stars_invoice(chat_id, months)
    except Exception as e:
        print(f"[stars-invoice-error] months={months} err={e}", file=sys.stderr, flush=True)
        send_message(
            chat_id,
            "❌ Не удалось открыть оплату Stars.\nПроверь настройки платежей в BotFather или попробуй позже.",
            kb_pay(),
        )


def show_support(msg: dict):
    send_message(msg["chat"]["id"], SUPPORT_TEXT, kb_support())


def show_admin(msg: dict):
    user = msg["from"]
    chat_id = msg["chat"]["id"]
    if not is_admin_user(user):
        send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
        return
    total = count_clients()
    text = f"Админка\nВсего пользователей: {total}\n\nВыберите раздел:"
    send_message(chat_id, text, kb_admin())


def show_admin_status(msg: dict):
    user = msg["from"]
    chat_id = msg["chat"]["id"]
    if not is_admin_user(user):
        send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
        return
    rc, out = run_cmd([METRICS_CMD], timeout_sec=45)
    if rc == 0:
        send_message(chat_id, out[:3500], kb_admin())
    else:
        text = "❌ Не удалось получить метрики узла.\n\n" + (out[:3000] if out else f"rc={rc}")
        send_message(chat_id, text, kb_admin())


def start_select(conn: sqlite3.Connection, msg: dict, intent: str, query: str = "", offset: int = 0):
    tg_id = int(msg["from"]["id"])
    chat_id = msg["chat"]["id"]
    filter_mode = "all"
    if intent == "block":
        filter_mode = "only_active"
    elif intent == "unblock":
        filter_mode = "only_blocked"
    elif intent == "trial_off":
        filter_mode = "only_trial"
    rows = build_user_rows(conn, query=query, filter_mode=filter_mode)
    if offset < 0:
        offset = 0
    if offset >= len(rows):
        offset = max(0, len(rows) - SELECT_PAGE_SIZE)
    page = rows[offset: offset + SELECT_PAGE_SIZE]

    set_admin_state(conn, tg_id, STATE_SELECT_USER, {"intent": intent, "query": query, "offset": offset})

    if intent == "view":
        title = "Список пользователей"
        can_choose = False
    elif intent == "edit":
        title = "Редактирование срока: выбери пользователя"
        can_choose = True
    elif intent == "block":
        title = "Блокировка: выбери пользователя"
        can_choose = True
    elif intent == "unblock":
        title = "Разблокировка: выбери пользователя"
        can_choose = True
    elif intent == "trial_off":
        title = "Снять триал: выбери пользователя"
        can_choose = True
    else:
        title = "Удаление: выбери пользователя"
        can_choose = True

    q_txt = f"\nФильтр: {query}" if query else ""
    line_items = []
    for i, r in enumerate(page, start=offset + 1):
        line_items.append(f"{i}. {r['display']} | {r['exp_txt']} | {r['status']}")
    body = "\n".join(line_items) if line_items else "(пусто)"
    text = f"{title}\nВсего: {len(rows)}{q_txt}\n\n{body}"
    send_message(chat_id, text, kb_selector(page, offset, len(rows), can_choose=can_choose))


def start_search(conn: sqlite3.Connection, msg: dict, intent: str):
    tg_id = int(msg["from"]["id"])
    set_admin_state(conn, tg_id, STATE_SEARCH_QUERY, {"intent": intent})
    send_message(msg["chat"]["id"], "Введи имя или часть имени пользователя для поиска:", kb_admin_back())


def handle_admin_text(conn: sqlite3.Connection, msg: dict, text: str, st: dict):
    tg_id = int(msg["from"]["id"])
    chat_id = msg["chat"]["id"]
    step = st.get("step")
    payload = st.get("payload") or {}

    if step == STATE_ADD_NAME:
        name = text.strip()
        if not is_valid_name(name):
            send_message(chat_id, "Некорректное имя. Разрешено: A-Z a-z 0-9 . _ -", kb_admin_back())
            return True
        if master_has_vpn_user(name):
            send_message(chat_id, "Пользователь уже существует. Введи другое имя.", kb_admin_back())
            return True
        set_admin_state(conn, tg_id, STATE_ADD_DAYS, {"name": name})
        send_message(chat_id, f"Имя: {name}\nВведи срок в днях:", kb_admin_back())
        return True

    if step == STATE_ADD_DAYS:
        days = parse_positive_int(text)
        if days is None:
            send_message(chat_id, "Некорректное значение. Введи целое число дней > 0.", kb_admin_back())
            return True
        name = payload.get("name", "")
        rc, out = run_cmd([ADD_USER_CMD, "--name", name, "--days", str(days)], timeout_sec=300)
        clear_admin_state(conn, tg_id)
        if rc == 0:
            print(f"[admin-add-ok] name={name} days={days}", file=sys.stderr, flush=True)
            send_message(chat_id, f"✅ Пользователь добавлен: {name}\nСрок: {days} дн.", kb_admin())
        else:
            send_message(chat_id, f"❌ Не удалось добавить пользователя {name}.\n\n{out[:1200]}", kb_admin())
        return True

    if step == STATE_EDIT_DAYS:
        days = parse_positive_int(text)
        if days is None:
            send_message(chat_id, "Некорректное значение. Введи целое число дней > 0.", kb_admin_back())
            return True
        name = payload.get("name", "")
        ok, out = set_user_expire_days(name, days)
        clear_admin_state(conn, tg_id)
        if ok:
            send_message(chat_id, f"✅ Срок обновлен: {name}\nНовый срок: {days} дн.", kb_admin())
            info = find_subscription_info(name)
            exp_txt = (info or {}).get("expire_text", "обновлено")
            notify_user_change(
                conn,
                name,
                f"🔔 Администратор обновил срок вашей подписки.\n"
                f"Новый срок: {days} дн.\n"
                f"Действует до: {exp_txt}",
            )
        else:
            send_message(chat_id, f"❌ Не удалось обновить срок для {name}.\n\n{out[:1200]}", kb_admin())
        return True

    if step in (STATE_BLOCK_CONFIRM, STATE_UNBLOCK_CONFIRM, STATE_TRIAL_OFF_CONFIRM, STATE_DEL_CONFIRM):
        send_message(chat_id, "Подтверждение выполняется кнопкой «✅ Подтвердить».", kb_admin_back())
        return True

    if step == STATE_SEARCH_QUERY:
        query = text.strip()
        intent = payload.get("intent", "view")
        start_select(conn, msg, intent=intent, query=query, offset=0)
        return True

    return False


def handle_confirm_callback(conn: sqlite3.Connection, msg: dict, action: str, st: dict):
    tg_id = int(msg["from"]["id"])
    chat_id = msg["chat"]["id"]
    step = st.get("step")
    payload = st.get("payload") or {}
    name = payload.get("name", "")

    if step == STATE_BLOCK_CONFIRM and action == CB_CONFIRM_BLOCK:
        ok, out = set_user_blocked(name, blocked=True)
        clear_admin_state(conn, tg_id)
        if ok:
            send_message(chat_id, f"✅ Пользователь заблокирован: {name}", kb_admin())
            notify_user_change(
                conn,
                name,
                "⛔ Администратор изменил статус вашей подписки: доступ временно приостановлен.\n"
                "Если это ошибка, напишите в поддержку.",
            )
        else:
            send_message(chat_id, f"❌ Не удалось заблокировать {name}.\n\n{out[:1200]}", kb_admin())
        return True

    if step == STATE_UNBLOCK_CONFIRM and action == CB_CONFIRM_UNBLOCK:
        ok, out = set_user_blocked(name, blocked=False)
        clear_admin_state(conn, tg_id)
        if ok:
            send_message(chat_id, f"✅ Пользователь разблокирован: {name}", kb_admin())
            notify_user_change(
                conn,
                name,
                "✅ Администратор изменил статус вашей подписки: доступ восстановлен.",
            )
        else:
            send_message(chat_id, f"❌ Не удалось разблокировать {name}.\n\n{out[:1200]}", kb_admin())
        return True

    if step == STATE_TRIAL_OFF_CONFIRM and action == CB_CONFIRM_TRIAL_OFF:
        ok, out = set_user_trial(name, is_trial=False)
        clear_admin_state(conn, tg_id)
        if ok:
            send_message(chat_id, f"✅ Триал снят: {name}", kb_admin())
            notify_user_change(
                conn,
                name,
                "🔔 Администратор отключил пробный статус вашей подписки.",
            )
        else:
            send_message(chat_id, f"❌ Не удалось снять триал у {name}.\n\n{out[:1200]}", kb_admin())
        return True

    if step == STATE_DEL_CONFIRM and action == CB_CONFIRM_DELETE:
        rc, out = run_cmd([DEL_USER_CMD, "--name", name], timeout_sec=300)
        clear_admin_state(conn, tg_id)
        if rc == 0:
            notify_user_change(
                conn,
                name,
                "🗑 Администратор удалил вашу подписку.\n"
                "Для повторного доступа напишите /start.",
            )
            delete_tg_users_by_vpn_name(conn, name)
            print(f"[admin-del-ok] name={name}", file=sys.stderr, flush=True)
            send_message(chat_id, f"✅ Пользователь удален: {name}\nУдален и из бота (tg_users).", kb_admin())
        else:
            send_message(chat_id, f"❌ Не удалось удалить {name}.\n\n{out[:1200]}", kb_admin())
        return True

    return False


def handle_start(conn: sqlite3.Connection, msg: dict):
    user = msg["from"]
    tg_id = int(user["id"])
    username = user.get("username") or ""
    clear_admin_state(conn, tg_id)

    row = get_user(conn, tg_id)
    if row:
        last_start = int(row[4] or 0)
        now = int(time.time())
        if now - last_start < START_RATE_LIMIT_SEC:
            show_main(msg["chat"]["id"], user)
            return
        touch_start(conn, tg_id)
        show_main(msg["chat"]["id"], user)
        return

    pending = get_pending_provision_job(conn, tg_id)
    if pending:
        send_message(
            msg["chat"]["id"],
            "⏳ Подписка еще создается. Это может занять до 1-2 минут.",
            kb_main(is_admin=is_admin_user(user)),
        )
        return

    vpn_name = f"tg_{tg_id}"
    enqueue_provision_job(conn, tg_id, int(msg["chat"]["id"]), username, vpn_name)
    send_message(
        msg["chat"]["id"],
        "⏳ Начал создавать подписку. Это обычно занимает 30-90 секунд.\nЯ пришлю сообщение, когда будет готово.",
        kb_main(is_admin=is_admin_user(user)),
    )


def handle_selector_callback(conn: sqlite3.Connection, msg: dict, action: str, st: dict):
    payload = st.get("payload") or {}
    intent = payload.get("intent", "view")
    query = payload.get("query", "")
    offset = int(payload.get("offset", 0) or 0)
    tg_id = int(msg["from"]["id"])
    chat_id = msg["chat"]["id"]

    rows = build_user_rows(conn, query=query)

    if action == CB_SEL_PREV:
        start_select(conn, msg, intent=intent, query=query, offset=max(0, offset - SELECT_PAGE_SIZE))
        return True

    if action == CB_SEL_NEXT:
        start_select(conn, msg, intent=intent, query=query, offset=offset + SELECT_PAGE_SIZE)
        return True

    if action == CB_SEL_FIND:
        start_search(conn, msg, intent=intent)
        return True

    if action.startswith(CB_SEL_USER_PREFIX):
        if intent == "view":
            send_message(chat_id, "Для списка используй поиск/листание. Выбор пользователя не требуется.", kb_admin())
            clear_admin_state(conn, tg_id)
            return True

        name = action[len(CB_SEL_USER_PREFIX):].strip()
        if not master_has_vpn_user(name):
            send_message(chat_id, "Пользователь не найден (возможно уже удален).", kb_admin())
            clear_admin_state(conn, tg_id)
            return True

        if intent == "edit":
            set_admin_state(conn, tg_id, STATE_EDIT_DAYS, {"name": name})
            send_message(chat_id, f"Пользователь: {name}\nВведи новый срок в днях:", kb_admin_back())
            return True
        if intent == "block":
            set_admin_state(conn, tg_id, STATE_BLOCK_CONFIRM, {"name": name})
            send_message(chat_id, f"Подтвердить блокировку пользователя {name}?", kb_confirm(CB_CONFIRM_BLOCK))
            return True
        if intent == "unblock":
            set_admin_state(conn, tg_id, STATE_UNBLOCK_CONFIRM, {"name": name})
            send_message(chat_id, f"Подтвердить разблокировку пользователя {name}?", kb_confirm(CB_CONFIRM_UNBLOCK))
            return True
        if intent == "trial_off":
            set_admin_state(conn, tg_id, STATE_TRIAL_OFF_CONFIRM, {"name": name})
            send_message(chat_id, f"Подтвердить снятие триала у пользователя {name}?", kb_confirm(CB_CONFIRM_TRIAL_OFF))
            return True
        if intent == "del":
            set_admin_state(conn, tg_id, STATE_DEL_CONFIRM, {"name": name})
            send_message(chat_id, f"Подтвердить удаление пользователя {name}?", kb_confirm(CB_CONFIRM_DELETE))
            return True

    return False


def dispatch_action(conn: sqlite3.Connection, msg: dict, action: str):
    chat_id = msg["chat"]["id"]
    user = msg["from"]
    tg_id = int(user["id"])

    st = get_admin_state(conn, tg_id)
    if st and st.get("step") == STATE_SELECT_USER and action.startswith((CB_SEL_USER_PREFIX, CB_SEL_PREV, CB_SEL_NEXT, CB_SEL_FIND)):
        if handle_selector_callback(conn, msg, action, st):
            return
    if st and is_admin_user(user) and action in (
        CB_CONFIRM_BLOCK,
        CB_CONFIRM_UNBLOCK,
        CB_CONFIRM_TRIAL_OFF,
        CB_CONFIRM_DELETE,
    ):
        if handle_confirm_callback(conn, msg, action, st):
            return

    if action in (CB_MAIN, "Вернутся назад", "⬅️ Вернутся назад", "Вернуться назад", "⬅️ Вернуться назад"):
        clear_admin_state(conn, tg_id)
        show_main(chat_id, user)
    elif action in (CB_MY_SUB, "Моя подписка", "👤 Моя подписка"):
        clear_admin_state(conn, tg_id)
        show_my_subscription(conn, msg)
    elif action in (CB_PAY, "Оплатить подписку", "💰 Оплатить подписку"):
        clear_admin_state(conn, tg_id)
        show_pay(msg)
    elif action == CB_PAY_BACK:
        show_pay(msg)
    elif action == CB_PAY_TARIFF_1:
        show_pay_plan(msg, 1)
    elif action == CB_PAY_TARIFF_3:
        show_pay_plan(msg, 3)
    elif action == CB_PAY_TARIFF_6:
        show_pay_plan(msg, 6)
    elif action == CB_PAY_TARIFF_12:
        show_pay_plan(msg, 12)
    elif action == CB_PAY_INVOICE_1:
        start_stars_payment(msg, 1)
    elif action == CB_PAY_INVOICE_3:
        start_stars_payment(msg, 3)
    elif action == CB_PAY_INVOICE_6:
        start_stars_payment(msg, 6)
    elif action == CB_PAY_INVOICE_12:
        start_stars_payment(msg, 12)
    elif action in (CB_SUPPORT, "Поддержка", "❓ Поддержка"):
        clear_admin_state(conn, tg_id)
        show_support(msg)
    elif action in (CB_ADMIN, "Админка", "🛠 Админка"):
        clear_admin_state(conn, tg_id)
        show_admin(msg)
    elif action == CB_ADMIN_USERS:
        if not is_admin_user(user):
            send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
            return
        send_message(chat_id, "Раздел «Пользователи».\nВыберите действие:", kb_admin_users())
    elif action == CB_ADMIN_ACCESS:
        if not is_admin_user(user):
            send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
            return
        send_message(chat_id, "Раздел «Доступ».\nВыберите действие:", kb_admin_access())
    elif action == CB_ADMIN_SERVICE:
        if not is_admin_user(user):
            send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
            return
        send_message(chat_id, "Раздел «Сервис».\nВыберите действие:", kb_admin_service())
    elif action == CB_ADMIN_CANCEL:
        clear_admin_state(conn, tg_id)
        show_admin(msg)
    elif action == CB_ADMIN_LIST:
        if not is_admin_user(user):
            send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
            return
        start_select(conn, msg, intent="view", query="", offset=0)
    elif action == CB_ADMIN_FIND:
        if not is_admin_user(user):
            send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
            return
        start_search(conn, msg, intent="view")
    elif action in (CB_ADMIN_STATUS, "/health", "📊 Состояние узла", "Состояние узла"):
        show_admin_status(msg)
    elif action == CB_ADMIN_ADD:
        if not is_admin_user(user):
            send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
            return
        set_admin_state(conn, tg_id, STATE_ADD_NAME, {})
        send_message(chat_id, "Добавление пользователя\n\nВведи имя (латиница/цифры/._-):", kb_admin_back())
    elif action == CB_ADMIN_EDIT:
        if not is_admin_user(user):
            send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
            return
        start_select(conn, msg, intent="edit", query="", offset=0)
    elif action == CB_ADMIN_BLOCK:
        if not is_admin_user(user):
            send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
            return
        start_select(conn, msg, intent="block", query="", offset=0)
    elif action == CB_ADMIN_UNBLOCK:
        if not is_admin_user(user):
            send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
            return
        start_select(conn, msg, intent="unblock", query="", offset=0)
    elif action == CB_ADMIN_TRIAL_OFF:
        if not is_admin_user(user):
            send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
            return
        start_select(conn, msg, intent="trial_off", query="", offset=0)
    elif action == CB_ADMIN_DEL:
        if not is_admin_user(user):
            send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
            return
        start_select(conn, msg, intent="del", query="", offset=0)
    else:
        if st and is_admin_user(user):
            if handle_admin_text(conn, msg, action, st):
                return
        show_main(chat_id, user)


def main_loop():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    ensure_bot_menu_commands()

    worker = Thread(target=provision_worker_loop, daemon=True)
    worker.start()
    monitor = Thread(target=monitor_loop, daemon=True)
    monitor.start()
    trial_notifier = Thread(target=trial_notice_loop, daemon=True)
    trial_notifier.start()

    offset = 0
    while True:
        try:
            updates = api_call("getUpdates", {"timeout": 30, "offset": offset})
            for upd in updates:
                offset = max(offset, int(upd["update_id"]) + 1)

                pcq = upd.get("pre_checkout_query")
                if pcq:
                    pcq_id = pcq.get("id")
                    if pcq_id:
                        answer_pre_checkout(pcq_id, True)
                    continue

                cq = upd.get("callback_query")
                if cq:
                    msg = cq.get("message")
                    actor = cq.get("from")
                    if msg:
                        if actor:
                            msg["from"] = actor
                        data = (cq.get("data") or "").strip()
                        dispatch_action(conn, msg, data)
                    answer_callback(cq.get("id"))
                    continue

                msg = upd.get("message")
                if not msg:
                    continue

                successful = msg.get("successful_payment")
                if successful:
                    user = msg.get("from") or {}
                    tg_id = int(user.get("id") or 0)
                    row = get_user(conn, tg_id)
                    payload = (successful.get("invoice_payload") or "").strip().lower()
                    m = re.fullmatch(r"sub_(\d+)m", payload)
                    months = int(m.group(1)) if m else 0
                    plan = PAYMENT_PLANS.get(months)
                    if not row or not plan:
                        send_message(
                            int(msg["chat"]["id"]),
                            "✅ Оплата получена. Напиши в поддержку для ручной активации.\n\n" + SUPPORT_TEXT,
                            kb_main(is_admin=is_admin_user(user)),
                        )
                        send_admin_alert(
                            f"💳 Получена оплата Stars, но не удалось авто-продлить.\n"
                            f"tg_id={tg_id} payload={payload or '-'}"
                        )
                        continue

                    vpn_name = row[2]
                    days = int(plan["days"])
                    ok, out = extend_user_expire_days(vpn_name, days)
                    if ok:
                        set_trial_flag(vpn_name, False)
                        info = find_subscription_info(vpn_name)
                        exp_txt = (info or {}).get("expire_text", "обновлено")
                        send_message(
                            int(msg["chat"]["id"]),
                            f"✅ Оплата получена. Подписка продлена на {months} мес.\nДействует до: {exp_txt}",
                            kb_main(is_admin=is_admin_user(user)),
                        )
                    else:
                        send_message(
                            int(msg["chat"]["id"]),
                            "✅ Оплата получена.\n❌ Не удалось авто-продлить срок, напиши в поддержку.\n\n" + SUPPORT_TEXT,
                            kb_main(is_admin=is_admin_user(user)),
                        )
                        send_admin_alert(
                            f"💳 Оплата получена, но продление не применилось.\n"
                            f"user={vpn_name} tg_id={tg_id} payload={payload or '-'}\n{out[:1200]}"
                        )
                    continue

                text = (msg.get("text") or "").strip()
                if not text:
                    continue

                if text.startswith("/start"):
                    handle_start(conn, msg)
                    continue

                user = msg.get("from") or {}
                tg_id = int(user.get("id") or 0)
                st = get_admin_state(conn, tg_id)
                if st and is_admin_user(user):
                    if handle_admin_text(conn, msg, text, st):
                        continue

                dispatch_action(conn, msg, text)

        except Exception as e:
            print(f"loop error: {e}", file=sys.stderr)
            traceback.print_exc()
            time.sleep(2)


if __name__ == "__main__":
    main_loop()
