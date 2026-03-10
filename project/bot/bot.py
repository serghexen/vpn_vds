#!/usr/bin/env python3
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import traceback
import hashlib
import html
import shlex
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
REPLICA_MONITOR_ENABLED = os.environ.get("REPLICA_MONITOR_ENABLED", "0").strip() == "1"
REPLICA_MONITOR_INTERVAL_SEC = int(os.environ.get("REPLICA_MONITOR_INTERVAL_SEC", "300"))
REPLICA_MONITOR_COOLDOWN_SEC = int(os.environ.get("REPLICA_MONITOR_COOLDOWN_SEC", "1800"))
REPLICA_MONITOR_CMD = os.environ.get("REPLICA_MONITOR_CMD", "/usr/local/sbin/healthcheck-replica")
REPLICA_OPS_CMD = os.environ.get("REPLICA_OPS_CMD", "/usr/local/sbin/replica-ops")
METRICS_CMD = os.environ.get("METRICS_CMD", "/usr/local/sbin/metrics-master-light")
DEVICE_LOG_PATH = os.environ.get("DEVICE_LOG_PATH", "/var/log/nginx/sub_access.log")
DEVICE_BOOTSTRAP_BYTES = int(os.environ.get("DEVICE_BOOTSTRAP_BYTES", str(2 * 1024 * 1024)))
DEVICE_LIST_LIMIT = int(os.environ.get("DEVICE_LIST_LIMIT", "12"))
DEVICE_SOFT_LIMIT = int(os.environ.get("DEVICE_SOFT_LIMIT", "5"))
ONLINE_WINDOW_SEC = int(os.environ.get("ONLINE_WINDOW_SEC", "900"))
LIVE_ONLINE_ENABLED = os.environ.get("LIVE_ONLINE_ENABLED", "1").strip() == "1"
LIVE_ONLINE_SAMPLE_SEC = int(os.environ.get("LIVE_ONLINE_SAMPLE_SEC", "3"))
LIVE_ONLINE_TIMEOUT_SEC = int(os.environ.get("LIVE_ONLINE_TIMEOUT_SEC", "12"))
LIVE_ONLINE_CACHE_TTL_SEC = int(os.environ.get("LIVE_ONLINE_CACHE_TTL_SEC", "20"))
TRAFFIC_COLLECT_ENABLED = os.environ.get("TRAFFIC_COLLECT_ENABLED", "1").strip() == "1"
TRAFFIC_COLLECT_INTERVAL_SEC = int(os.environ.get("TRAFFIC_COLLECT_INTERVAL_SEC", "300"))
TRAFFIC_RETENTION_DAYS = int(os.environ.get("TRAFFIC_RETENTION_DAYS", "14"))
SSH_KEY_DEFAULT = "/root/.ssh/vless_sync_ed25519"
SSH_KEY = os.environ.get("SSH_KEY", SSH_KEY_DEFAULT).strip() or SSH_KEY_DEFAULT
UK_HOST = os.environ.get("UK_HOST", "").strip()
TR_HOST = os.environ.get("TR_HOST", "").strip()
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
CB_ADMIN_DEVICES = "admin_devices"
CB_ADMIN_DEVICES_REFRESH = "admin_devices_refresh"
CB_ADMIN_ONLINE = "admin_online"
CB_ADMIN_TRAFFIC = "admin_traffic"
CB_ADMIN_TRAFFIC_PICK = "admin_traffic_pick"
CB_ADMIN_TRAFFIC_REFRESH = "admin_traffic_refresh"
CB_ADMIN_RESTART_UK = "admin_restart_uk"
CB_ADMIN_RESTART_TR = "admin_restart_tr"
CB_ADMIN_CANCEL = "admin_cancel"
CB_CONFIRM_BLOCK = "confirm_block"
CB_CONFIRM_UNBLOCK = "confirm_unblock"
CB_CONFIRM_TRIAL_OFF = "confirm_trial_off"
CB_CONFIRM_DELETE = "confirm_delete"
CB_CONFIRM_RESTART_UK = "confirm_restart_uk"
CB_CONFIRM_RESTART_TR = "confirm_restart_tr"
CB_SEL_PREV = "sel_prev"
CB_SEL_NEXT = "sel_next"
CB_SEL_FIND = "sel_find"
CB_SEL_USER_PREFIX = "sel_user:"
CB_MY_DEVICES = "my_devices"
CB_MY_DEVICE_REVOKE_ALL = "mydev_del_all"
CB_MY_DEVICE_REVOKE_PREFIX = "mydev_del:"

STATE_ADD_NAME = "add_name"
STATE_ADD_DAYS = "add_days"
STATE_EDIT_DAYS = "edit_days"
STATE_BLOCK_CONFIRM = "block_confirm"
STATE_UNBLOCK_CONFIRM = "unblock_confirm"
STATE_TRIAL_OFF_CONFIRM = "trial_off_confirm"
STATE_DEL_CONFIRM = "del_confirm"
STATE_RESTART_UK_CONFIRM = "restart_uk_confirm"
STATE_RESTART_TR_CONFIRM = "restart_tr_confirm"
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

_live_cache = {"ts": 0, "data": None}


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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vpn_name TEXT NOT NULL,
            device_key TEXT NOT NULL,
            hwid TEXT NOT NULL DEFAULT '',
            user_agent TEXT NOT NULL DEFAULT '',
            ip TEXT NOT NULL DEFAULT '',
            platform TEXT NOT NULL DEFAULT '',
            os_name TEXT NOT NULL DEFAULT '',
            os_version TEXT NOT NULL DEFAULT '',
            device_model TEXT NOT NULL DEFAULT '',
            app_version TEXT NOT NULL DEFAULT '',
            lang TEXT NOT NULL DEFAULT '',
            first_seen INTEGER NOT NULL,
            last_seen INTEGER NOT NULL,
            hits INTEGER NOT NULL DEFAULT 1,
            revoked INTEGER NOT NULL DEFAULT 0,
            pending INTEGER NOT NULL DEFAULT 0,
            last_path TEXT NOT NULL DEFAULT '',
            UNIQUE(vpn_name, device_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS device_ingest_state (
            log_path TEXT PRIMARY KEY,
            inode INTEGER NOT NULL,
            offset INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS traffic_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collected_at INTEGER NOT NULL,
            node TEXT NOT NULL,
            node_host TEXT NOT NULL DEFAULT '',
            vpn_name TEXT NOT NULL,
            uplink_total INTEGER NOT NULL DEFAULT 0,
            downlink_total INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    # lightweight migration for existing DBs
    cols = [r[1] for r in conn.execute("PRAGMA table_info(user_devices)").fetchall()]
    if "revoked" not in cols:
        conn.execute("ALTER TABLE user_devices ADD COLUMN revoked INTEGER NOT NULL DEFAULT 0")
    if "platform" not in cols:
        conn.execute("ALTER TABLE user_devices ADD COLUMN platform TEXT NOT NULL DEFAULT ''")
    if "os_name" not in cols:
        conn.execute("ALTER TABLE user_devices ADD COLUMN os_name TEXT NOT NULL DEFAULT ''")
    if "os_version" not in cols:
        conn.execute("ALTER TABLE user_devices ADD COLUMN os_version TEXT NOT NULL DEFAULT ''")
    if "device_model" not in cols:
        conn.execute("ALTER TABLE user_devices ADD COLUMN device_model TEXT NOT NULL DEFAULT ''")
    if "app_version" not in cols:
        conn.execute("ALTER TABLE user_devices ADD COLUMN app_version TEXT NOT NULL DEFAULT ''")
    if "lang" not in cols:
        conn.execute("ALTER TABLE user_devices ADD COLUMN lang TEXT NOT NULL DEFAULT ''")
    if "pending" not in cols:
        conn.execute("ALTER TABLE user_devices ADD COLUMN pending INTEGER NOT NULL DEFAULT 0")
    normalize_tg_alias_devices(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_devices_vpn_last ON user_devices(vpn_name, last_seen DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_traffic_samples_time ON traffic_samples(collected_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_traffic_samples_user ON traffic_samples(vpn_name, collected_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_traffic_samples_node ON traffic_samples(node, collected_at)")
    conn.commit()


def canonical_vpn_name(conn: sqlite3.Connection, vpn_name: str):
    name = (vpn_name or "").strip()
    m = re.fullmatch(r"tg_(\d+)", name)
    if not m:
        return name
    try:
        tg_id = int(m.group(1))
    except Exception:
        return name
    cur = conn.execute("SELECT vpn_name FROM tg_users WHERE tg_id=? LIMIT 1", (tg_id,))
    row = cur.fetchone()
    mapped = ((row or [""])[0] or "").strip()
    return mapped or name


def normalize_tg_alias_devices(conn: sqlite3.Connection):
    rows = conn.execute("SELECT tg_id, vpn_name FROM tg_users").fetchall()
    moved = 0
    for tg_id, canonical in rows:
        canonical = (canonical or "").strip()
        if not canonical:
            continue
        alias = f"tg_{int(tg_id)}"
        if alias == canonical:
            continue
        conn.execute(
            """
            DELETE FROM user_devices
            WHERE vpn_name=? AND device_key IN (
                SELECT device_key FROM user_devices WHERE vpn_name=?
            )
            """,
            (alias, canonical),
        )
        cur = conn.execute("UPDATE user_devices SET vpn_name=? WHERE vpn_name=?", (canonical, alias))
        moved += int(cur.rowcount or 0)
    if moved > 0:
        print(f"[devices-normalize] moved={moved}", file=sys.stderr, flush=True)


def count_active_devices(conn: sqlite3.Connection, vpn_name: str):
    cur = conn.execute(
        "SELECT COUNT(*) FROM user_devices WHERE vpn_name=? AND revoked=0 AND pending=0",
        (vpn_name,),
    )
    row = cur.fetchone()
    return int((row or [0])[0] or 0)


def user_last_seen_ts(conn: sqlite3.Connection, vpn_name: str):
    cur = conn.execute(
        "SELECT MAX(last_seen) FROM user_devices WHERE vpn_name=? AND revoked=0",
        (vpn_name,),
    )
    row = cur.fetchone()
    return int((row or [0])[0] or 0)


def is_user_online(last_seen_ts: int):
    if int(last_seen_ts or 0) <= 0:
        return False
    return (int(time.time()) - int(last_seen_ts)) <= ONLINE_WINDOW_SEC


def online_label(last_seen_ts: int):
    if is_user_online(last_seen_ts):
        return "🟢 онлайн"
    return "⚪ офлайн"


def online_users_count(conn: sqlite3.Connection):
    now = int(time.time())
    threshold = now - ONLINE_WINDOW_SEC
    cur = conn.execute(
        """
        SELECT COUNT(*)
        FROM (
          SELECT vpn_name, MAX(last_seen) AS mx
          FROM user_devices
          WHERE revoked=0
          GROUP BY vpn_name
        ) t
        WHERE mx >= ?
        """,
        (threshold,),
    )
    row = cur.fetchone()
    return int((row or [0])[0] or 0)


def _extract_json_obj(raw: str):
    s = (raw or "").strip()
    if not s:
        return {}
    i = s.find("{")
    j = s.rfind("}")
    if i < 0 or j < i:
        return {}
    try:
        return json.loads(s[i : j + 1])
    except Exception:
        return {}


def _parse_user_traffic_stats(raw: str):
    obj = _extract_json_obj(raw)
    stats = {}
    for it in obj.get("stat", []) or []:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "")
        val = int(it.get("value") or 0)
        m = re.fullmatch(r"user>>>(.+)>>>traffic>>>(uplink|downlink)", name)
        if not m:
            continue
        user = (m.group(1) or "").strip()
        kind = m.group(2)
        if not user:
            continue
        rec = stats.setdefault(user, {"uplink": 0, "downlink": 0})
        rec[kind] = val
    return stats


def _statsquery_local():
    # master can run xray in docker; query via host namespace if available.
    cmd = (
        "nsenter -t 1 -m -u -i -n -p sh -lc "
        + shlex.quote("docker exec hexenvpn-xray /usr/local/bin/xray api statsquery --server=127.0.0.1:10085")
    )
    rc, out = run_cmd(["sh", "-lc", cmd], timeout_sec=LIVE_ONLINE_TIMEOUT_SEC)
    return rc, out


def _statsquery_remote(host: str):
    args = [
        "ssh",
        "-i",
        SSH_KEY,
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "ConnectTimeout=8",
        f"root@{host}",
        "/usr/local/bin/xray api statsquery --server=127.0.0.1:10085",
    ]
    return run_cmd(args, timeout_sec=LIVE_ONLINE_TIMEOUT_SEC)


def _collect_traffic_node(kind: str, host: str):
    if kind == "master":
        rc, out = _statsquery_local()
        node = "master"
        node_host = ""
    else:
        rc, out = _statsquery_remote(host)
        node = kind
        node_host = host
    if rc != 0:
        return {"ok": False, "node": node, "node_host": node_host, "error": (out or f"rc={rc}")[:180], "stats": {}}
    stats = _parse_user_traffic_stats(out)
    return {"ok": True, "node": node, "node_host": node_host, "error": "", "stats": stats}


def collect_traffic_snapshot(conn: sqlite3.Connection):
    now = int(time.time())
    entries = []
    results = []

    # Always try master.
    results.append(_collect_traffic_node("master", ""))
    if UK_HOST:
        results.append(_collect_traffic_node("uk", UK_HOST))
    if TR_HOST:
        results.append(_collect_traffic_node("tr", TR_HOST))

    for rec in results:
        if not rec.get("ok"):
            print(
                f"[traffic-collect-error] node={rec.get('node')} host={rec.get('node_host')} err={rec.get('error')}",
                file=sys.stderr,
                flush=True,
            )
            continue
        node = rec.get("node") or ""
        node_host = rec.get("node_host") or ""
        stats = rec.get("stats") or {}
        for vpn_name, tr in stats.items():
            name = (vpn_name or "").strip()
            if not name:
                continue
            uplink = int((tr or {}).get("uplink") or 0)
            downlink = int((tr or {}).get("downlink") or 0)
            entries.append((now, node, node_host, name, uplink, downlink))

    if entries:
        conn.executemany(
            """
            INSERT INTO traffic_samples (collected_at, node, node_host, vpn_name, uplink_total, downlink_total)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            entries,
        )

    # Retention
    keep_from = now - max(1, TRAFFIC_RETENTION_DAYS) * 86400
    conn.execute("DELETE FROM traffic_samples WHERE collected_at < ?", (keep_from,))
    conn.commit()
    return len(entries)


def traffic_collect_loop():
    if not TRAFFIC_COLLECT_ENABLED:
        print("[traffic-collect] disabled", file=sys.stderr, flush=True)
        return
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    print(
        f"[traffic-collect] enabled interval={TRAFFIC_COLLECT_INTERVAL_SEC}s retention={TRAFFIC_RETENTION_DAYS}d",
        file=sys.stderr,
        flush=True,
    )
    while True:
        try:
            n = collect_traffic_snapshot(conn)
            print(f"[traffic-collect] samples={n}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[traffic-collect-loop-error] {e}", file=sys.stderr, flush=True)
            traceback.print_exc()
        time.sleep(max(60, TRAFFIC_COLLECT_INTERVAL_SEC))


def _collect_live_users_for_node(kind: str, host: str):
    if kind == "master":
        rc1, out1 = _statsquery_local()
    else:
        rc1, out1 = _statsquery_remote(host)
    if rc1 != 0:
        return {"ok": False, "error": (out1 or f"rc={rc1}")[:180], "users": set()}
    s1 = _parse_user_traffic_stats(out1)
    time.sleep(max(1, LIVE_ONLINE_SAMPLE_SEC))
    if kind == "master":
        rc2, out2 = _statsquery_local()
    else:
        rc2, out2 = _statsquery_remote(host)
    if rc2 != 0:
        return {"ok": False, "error": (out2 or f"rc={rc2}")[:180], "users": set()}
    s2 = _parse_user_traffic_stats(out2)
    live = set()
    keys = set(s1.keys()) | set(s2.keys())
    for k in keys:
        a = s1.get(k, {})
        b = s2.get(k, {})
        du = int(b.get("uplink", 0)) - int(a.get("uplink", 0))
        dd = int(b.get("downlink", 0)) - int(a.get("downlink", 0))
        if (du + dd) > 0:
            live.add(k)
    return {"ok": True, "error": "", "users": live}


def get_live_online_snapshot(force: bool = False):
    now = int(time.time())
    cached = _live_cache.get("data")
    ts = int(_live_cache.get("ts") or 0)
    if not force and cached is not None and (now - ts) <= LIVE_ONLINE_CACHE_TTL_SEC:
        return cached

    if not LIVE_ONLINE_ENABLED:
        data = {"enabled": False, "nodes": {}, "all_users": set()}
        _live_cache["ts"] = now
        _live_cache["data"] = data
        return data

    nodes = {}
    # Pilot priority: UK/TR by SSH; master best-effort via local docker exec.
    if UK_HOST:
        nodes[f"uk:{UK_HOST}"] = _collect_live_users_for_node("remote", UK_HOST)
    if TR_HOST:
        nodes[f"tr:{TR_HOST}"] = _collect_live_users_for_node("remote", TR_HOST)
    nodes["master:local"] = _collect_live_users_for_node("master", "")

    all_users = set()
    for rec in nodes.values():
        if rec.get("ok"):
            all_users.update(rec.get("users") or set())

    data = {"enabled": True, "nodes": nodes, "all_users": all_users}
    _live_cache["ts"] = now
    _live_cache["data"] = data
    return data


def promote_pending_devices(conn: sqlite3.Connection, vpn_name: str):
    slots = DEVICE_SOFT_LIMIT - count_active_devices(conn, vpn_name)
    if slots <= 0:
        return 0
    cur = conn.execute(
        """
        SELECT device_key
        FROM user_devices
        WHERE vpn_name=? AND revoked=0 AND pending=1
        ORDER BY last_seen DESC
        LIMIT ?
        """,
        (vpn_name, int(slots)),
    )
    keys = [str(r[0]) for r in cur.fetchall() if r and r[0]]
    if not keys:
        return 0
    conn.executemany(
        "UPDATE user_devices SET pending=0 WHERE vpn_name=? AND device_key=?",
        [(vpn_name, k) for k in keys],
    )
    return len(keys)


def _safe_text(s: str, limit: int = 300):
    t = (s or "").replace("\n", " ").replace("\r", " ").strip()
    if len(t) > limit:
        return t[: limit - 1] + "…"
    return t


def _fmt_ts(ts: int):
    if ts <= 0:
        return "-"
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M")


def _resolve_vpn_name_by_sub_key(sub_key: str):
    key = (sub_key or "").strip()
    if not key:
        return ""
    for c in load_clients():
        name = (c.get("name") or "").strip()
        token = (c.get("token") or "").strip()
        if key == name or key == token:
            return name
    return ""


def _norm_field(raw: str):
    s = (raw or "").strip()
    if s in ("", "-", "null", "None"):
        return ""
    return s


def _sub_key_from_uri(uri: str):
    u = (uri or "").strip()
    if not u:
        return ""
    path = u.split("?", 1)[0]
    m = re.fullmatch(r"/sub/([A-Za-z0-9._-]+)", path)
    if not m:
        return ""
    return m.group(1)


def _device_key(
    hwid: str,
    ua: str,
    ip: str = "",
    lang: str = "",
    app_version: str = "",
    platform: str = "",
    os_name: str = "",
    os_version: str = "",
    device_model: str = "",
):
    h = _norm_field(hwid)
    if h:
        return "hwid:" + h.lower()
    fp_src = "|".join(
        [
            _norm_field(ua).lower(),
            _norm_field(ip),
            _norm_field(lang).lower(),
            _norm_field(app_version).lower(),
            _norm_field(platform).lower(),
            _norm_field(os_name).lower(),
            _norm_field(os_version).lower(),
            _norm_field(device_model).lower(),
        ]
    ).strip("|")
    if not fp_src:
        return "unknown"
    digest = hashlib.sha1(fp_src.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return "fp:" + digest


def ingest_device_log(conn: sqlite3.Connection):
    p = Path(DEVICE_LOG_PATH)
    if not p.exists():
        return 0
    try:
        st = p.stat()
    except Exception:
        return 0

    cur = conn.execute("SELECT inode, offset FROM device_ingest_state WHERE log_path=?", (str(p),))
    row = cur.fetchone()
    inode = int(st.st_ino)
    size = int(st.st_size)
    offset = 0
    if row:
        prev_inode = int(row[0] or 0)
        prev_offset = int(row[1] or 0)
        if prev_inode == inode and 0 <= prev_offset <= size:
            offset = prev_offset
    elif size > DEVICE_BOOTSTRAP_BYTES:
        offset = size - DEVICE_BOOTSTRAP_BYTES

    parsed = 0
    now = int(time.time())
    with p.open("r", encoding="utf-8", errors="ignore") as f:
        if offset > 0:
            f.seek(offset)
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 9:
                continue
            def p(i: int):
                if i < len(parts):
                    return _norm_field(parts[i])
                return ""

            try:
                ts = int(float(p(0)))
            except Exception:
                ts = now

            ip = p(1)
            uri = p(2)
            ua = p(3)
            hwid = p(4) or p(5) or p(6) or p(7) or p(8)
            device_name = p(9)
            platform = p(10)
            os_name = p(11)
            os_version = p(12)
            device_model = p(13) or device_name
            app_version = p(14) or p(15)
            lang = p(16)
            ch_ua = p(17)
            ch_platform = p(18)

            if not ua and ch_ua:
                ua = ch_ua
            if not platform and ch_platform:
                platform = ch_platform

            sub_key = _sub_key_from_uri(uri)
            if not sub_key:
                continue
            vpn_name = _resolve_vpn_name_by_sub_key(sub_key)
            if not vpn_name:
                continue
            vpn_name = canonical_vpn_name(conn, vpn_name)

            dkey = _device_key(
                hwid=hwid,
                ua=ua,
                ip=ip,
                lang=lang,
                app_version=app_version,
                platform=platform,
                os_name=os_name,
                os_version=os_version,
                device_model=device_model,
            )
            existing = conn.execute(
                "SELECT revoked, pending FROM user_devices WHERE vpn_name=? AND device_key=?",
                (vpn_name, dkey),
            ).fetchone()
            pending = 0
            if existing:
                was_pending = int(existing[1] or 0) == 1
                was_revoked = int(existing[0] or 0) == 1
                if was_pending:
                    pending = 1
                elif was_revoked and count_active_devices(conn, vpn_name) >= DEVICE_SOFT_LIMIT:
                    pending = 1
            elif count_active_devices(conn, vpn_name) >= DEVICE_SOFT_LIMIT:
                pending = 1
            conn.execute(
                """
                INSERT INTO user_devices (vpn_name, device_key, hwid, user_agent, ip, platform, os_name, os_version, device_model, app_version, lang, first_seen, last_seen, hits, revoked, pending, last_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)
                ON CONFLICT(vpn_name, device_key) DO UPDATE SET
                    hwid=CASE WHEN excluded.hwid != '' THEN excluded.hwid ELSE user_devices.hwid END,
                    user_agent=excluded.user_agent,
                    ip=excluded.ip,
                    platform=CASE WHEN excluded.platform != '' THEN excluded.platform ELSE user_devices.platform END,
                    os_name=CASE WHEN excluded.os_name != '' THEN excluded.os_name ELSE user_devices.os_name END,
                    os_version=CASE WHEN excluded.os_version != '' THEN excluded.os_version ELSE user_devices.os_version END,
                    device_model=CASE WHEN excluded.device_model != '' THEN excluded.device_model ELSE user_devices.device_model END,
                    app_version=CASE WHEN excluded.app_version != '' THEN excluded.app_version ELSE user_devices.app_version END,
                    lang=CASE WHEN excluded.lang != '' THEN excluded.lang ELSE user_devices.lang END,
                    last_seen=excluded.last_seen,
                    hits=user_devices.hits + 1,
                    revoked=0,
                    pending=excluded.pending,
                    last_path=excluded.last_path
                """,
                (vpn_name, dkey, hwid, ua, ip, platform, os_name, os_version, device_model, app_version, lang, ts, ts, pending, uri),
            )
            parsed += 1

        end_pos = f.tell()

    conn.execute(
        """
        INSERT INTO device_ingest_state (log_path, inode, offset, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(log_path) DO UPDATE SET inode=excluded.inode, offset=excluded.offset, updated_at=excluded.updated_at
        """,
        (str(p), inode, int(end_pos), now),
    )
    conn.commit()
    return parsed


def get_device_stats_by_user(conn: sqlite3.Connection, limit: int = 20):
    cur = conn.execute(
        """
        SELECT
          vpn_name,
          SUM(CASE WHEN revoked=0 AND pending=0 THEN 1 ELSE 0 END) AS active_devices,
          SUM(CASE WHEN revoked=0 AND pending=1 THEN 1 ELSE 0 END) AS pending_devices,
          MAX(last_seen) AS last_seen
        FROM user_devices
        GROUP BY vpn_name
        HAVING active_devices > 0 OR pending_devices > 0
        ORDER BY active_devices DESC, pending_devices DESC, last_seen DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    return cur.fetchall()


def get_device_counts_map(conn: sqlite3.Connection):
    cur = conn.execute(
        """
        SELECT
          vpn_name,
          SUM(CASE WHEN revoked=0 AND pending=0 THEN 1 ELSE 0 END) AS active_devices,
          SUM(CASE WHEN revoked=0 AND pending=1 THEN 1 ELSE 0 END) AS pending_devices
        FROM user_devices
        GROUP BY vpn_name
        """
    )
    out = {}
    for r in cur.fetchall():
        out[(r[0] or "").strip()] = (int(r[1] or 0), int(r[2] or 0))
    return out


def get_latest_device_for_user(conn: sqlite3.Connection, vpn_name: str):
    cur = conn.execute(
        """
        SELECT device_key, hwid, user_agent, platform, os_name, os_version, device_model, app_version, last_seen
        FROM user_devices
        WHERE vpn_name=? AND revoked=0
        ORDER BY pending ASC, last_seen DESC
        LIMIT 1
        """,
        (vpn_name,),
    )
    return cur.fetchone()


def get_devices_for_user(conn: sqlite3.Connection, vpn_name: str, limit: int = DEVICE_LIST_LIMIT):
    cur = conn.execute(
        """
        SELECT device_key, hwid, user_agent, ip, platform, os_name, os_version, device_model, app_version, lang, first_seen, last_seen, hits, pending
        FROM user_devices
        WHERE vpn_name=? AND revoked=0
        ORDER BY pending ASC, first_seen ASC, last_seen ASC
        LIMIT ?
        """,
        (vpn_name, int(limit)),
    )
    return cur.fetchall()


def _fmt_bytes(n: int):
    size = float(max(0, int(n or 0)))
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    idx = 0
    while size >= 1024.0 and idx < len(units) - 1:
        size /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(size)} {units[idx]}"
    return f"{size:.1f} {units[idx]}"


def _traffic_node_label(node: str, node_host: str):
    n = (node or "").strip()
    h = (node_host or "").strip()
    if n == "master":
        return "master"
    if h:
        return f"{n}:{h}"
    return n or "-"


def _traffic_window_aggregate(conn: sqlite3.Connection, since_ts: int):
    cur = conn.execute(
        """
        SELECT collected_at, node, node_host, vpn_name, uplink_total, downlink_total
        FROM traffic_samples
        WHERE collected_at >= ?
        ORDER BY collected_at ASC
        """,
        (int(since_ts),),
    )
    prev = {}
    agg = {}
    for collected_at, node, node_host, raw_name, up_total, down_total in cur.fetchall():
        name = canonical_vpn_name(conn, (raw_name or "").strip())
        if not name:
            continue
        node_label = _traffic_node_label(node, node_host)
        key = (name, node_label)
        up_total = int(up_total or 0)
        down_total = int(down_total or 0)
        p = prev.get(key)
        if p is None:
            prev[key] = (up_total, down_total, int(collected_at or 0))
            continue
        prev_up, prev_down, _prev_ts = p
        du = up_total - prev_up
        dd = down_total - prev_down
        # Counter reset: treat current value as delta since reset.
        if du < 0:
            du = up_total
        if dd < 0:
            dd = down_total
        if du < 0:
            du = 0
        if dd < 0:
            dd = 0
        prev[key] = (up_total, down_total, int(collected_at or 0))
        user_rec = agg.setdefault(name, {"uplink": 0, "downlink": 0, "nodes": {}, "last_ts": 0})
        user_rec["uplink"] += du
        user_rec["downlink"] += dd
        user_rec["last_ts"] = max(int(user_rec.get("last_ts") or 0), int(collected_at or 0))
        node_rec = user_rec["nodes"].setdefault(node_label, {"uplink": 0, "downlink": 0})
        node_rec["uplink"] += du
        node_rec["downlink"] += dd
    return agg


def get_traffic_top(conn: sqlite3.Connection, hours: int = 24, limit: int = 12):
    since_ts = int(time.time()) - max(1, int(hours)) * 3600
    agg = _traffic_window_aggregate(conn, since_ts)
    rows = []
    for name, rec in agg.items():
        up = int(rec.get("uplink") or 0)
        down = int(rec.get("downlink") or 0)
        total = up + down
        if total <= 0:
            continue
        rows.append(
            {
                "vpn_name": name,
                "uplink": up,
                "downlink": down,
                "total": total,
                "last_ts": int(rec.get("last_ts") or 0),
            }
        )
    rows.sort(key=lambda r: (r["total"], r["downlink"], r["uplink"]), reverse=True)
    return rows[: max(1, int(limit))]


def get_traffic_user_breakdown(conn: sqlite3.Connection, vpn_name: str, hours: int = 24):
    since_ts = int(time.time()) - max(1, int(hours)) * 3600
    agg = _traffic_window_aggregate(conn, since_ts)
    rec = agg.get((vpn_name or "").strip()) or {"uplink": 0, "downlink": 0, "nodes": {}, "last_ts": 0}
    nodes = []
    for node_name, nrec in (rec.get("nodes") or {}).items():
        up = int(nrec.get("uplink") or 0)
        down = int(nrec.get("downlink") or 0)
        total = up + down
        nodes.append({"node": node_name, "uplink": up, "downlink": down, "total": total})
    nodes.sort(key=lambda x: (x["total"], x["downlink"], x["uplink"]), reverse=True)
    return {
        "vpn_name": (vpn_name or "").strip(),
        "uplink": int(rec.get("uplink") or 0),
        "downlink": int(rec.get("downlink") or 0),
        "total": int(rec.get("uplink") or 0) + int(rec.get("downlink") or 0),
        "last_ts": int(rec.get("last_ts") or 0),
        "nodes": nodes,
    }


def get_all_devices_for_user(conn: sqlite3.Connection, vpn_name: str, limit: int = 200):
    cur = conn.execute(
        """
        SELECT device_key, hwid, user_agent, ip, platform, os_name, os_version, device_model, app_version, lang, first_seen, last_seen, hits, pending
        FROM user_devices
        WHERE vpn_name=? AND revoked=0
        ORDER BY pending ASC, first_seen ASC, last_seen ASC
        LIMIT ?
        """,
        (vpn_name, int(limit)),
    )
    return cur.fetchall()


def device_action_token(vpn_name: str, device_key: str):
    raw = f"{vpn_name}|{device_key}".encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()[:12]


def revoke_device_by_token(conn: sqlite3.Connection, vpn_name: str, token: str):
    for row in get_all_devices_for_user(conn, vpn_name, limit=300):
        dkey = (row[0] or "")
        if device_action_token(vpn_name, dkey) == token:
            conn.execute(
                "UPDATE user_devices SET revoked=1 WHERE vpn_name=? AND device_key=?",
                (vpn_name, dkey),
            )
            promoted = promote_pending_devices(conn, vpn_name)
            conn.commit()
            return True, promoted
    return False, 0


def revoke_all_devices(conn: sqlite3.Connection, vpn_name: str):
    cur = conn.execute(
        "UPDATE user_devices SET revoked=1 WHERE vpn_name=? AND revoked=0",
        (vpn_name,),
    )
    promoted = promote_pending_devices(conn, vpn_name)
    conn.commit()
    return int(cur.rowcount or 0), promoted


def device_line_label(idx: int, hwid: str, ua: str):
    ident = (hwid or "").strip()
    if ident:
        return f"{idx}. {ident[:18]}"
    ua = (ua or "").strip()
    if not ua:
        return f"{idx}. Устройство"
    return f"{idx}. {ua.split(' ')[0][:18]}"


def human_device_id(device_key: str, hwid: str):
    h = (hwid or "").strip()
    if h:
        return h
    k = (device_key or "").strip()
    if not k:
        return "—"
    if k.startswith("fp:"):
        return "fp_" + k[3:]
    return k


ANDROID_MODEL_MAP = {
    "SM-S916B": "Samsung Galaxy S23+",
}


def _guess_os_from_ua(ua: str):
    u = (ua or "").lower()
    if "android" in u:
        return "Android"
    if "iphone" in u or "ipad" in u or "/ios" in u or " ios " in u:
        return "iOS"
    if "windows" in u:
        return "Windows"
    if "mac os" in u or "macintosh" in u:
        return "macOS"
    return ""


def _human_model(model: str):
    m = (model or "").strip()
    if not m:
        return ""
    up = m.upper()
    if up in ANDROID_MODEL_MAP:
        return ANDROID_MODEL_MAP[up]
    if up.startswith("SM-"):
        return f"Samsung {up}"
    return m


def human_device_title(platform: str, os_name: str, os_version: str, device_model: str, ua: str):
    p = (platform or "").strip()
    o = (os_name or "").strip()
    v = (os_version or "").strip()
    m = _human_model(device_model)

    if not o:
        o = _guess_os_from_ua(ua)
    if not p and o:
        p = o

    os_part = o
    if v:
        os_part = f"{o} {v}".strip()

    if m and os_part:
        return f"{m} ({os_part})"
    if m:
        return m
    if os_part:
        return os_part
    if p:
        return p
    return ""


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


def replica_monitor_loop():
    if not REPLICA_MONITOR_ENABLED:
        print("[replica-monitor] disabled", file=sys.stderr, flush=True)
        return

    nodes = []
    if UK_HOST:
        nodes.append(("uk", "UK", UK_HOST))
    if TR_HOST:
        nodes.append(("tr", "TR", TR_HOST))
    if not nodes:
        print("[replica-monitor] no replica hosts configured", file=sys.stderr, flush=True)
        return

    states = {code: {"was_bad": False, "last_bad_at": 0, "last_bad_sig": ""} for code, _label, _host in nodes}
    print(
        f"[replica-monitor] enabled interval={REPLICA_MONITOR_INTERVAL_SEC}s cooldown={REPLICA_MONITOR_COOLDOWN_SEC}s cmd={REPLICA_MONITOR_CMD}",
        file=sys.stderr,
        flush=True,
    )

    while True:
        try:
            now = int(time.time())
            for code, label, host in nodes:
                st = states.setdefault(code, {"was_bad": False, "last_bad_at": 0, "last_bad_sig": ""})
                args = [REPLICA_MONITOR_CMD, "--node", code]
                if MONITOR_CHECK_USER:
                    args += ["--user", MONITOR_CHECK_USER]
                rc, out = run_cmd(args, timeout_sec=max(60, min(REPLICA_MONITOR_INTERVAL_SEC, 180)))
                sig = f"{rc}:{(out or '')[:300]}"

                if rc == 0:
                    if st["was_bad"]:
                        send_admin_alert(f"✅ Мониторинг реплики {label}: восстановлено ({host}).")
                        print(f"[replica-monitor] recovered node={code}", file=sys.stderr, flush=True)
                    st["was_bad"] = False
                    continue

                need_alert = (not st["was_bad"]) or (
                    sig != st["last_bad_sig"] and (now - int(st["last_bad_at"] or 0)) >= REPLICA_MONITOR_COOLDOWN_SEC
                )
                if need_alert:
                    msg = f"🚨 Мониторинг реплики {label}: проблема ({host}).\n\n" + (out[:2500] if out else f"rc={rc}")
                    send_admin_alert(msg)
                    st["last_bad_at"] = now
                    st["last_bad_sig"] = sig
                    print(f"[replica-monitor] alerted node={code}", file=sys.stderr, flush=True)
                st["was_bad"] = True
        except Exception as e:
            print(f"[replica-monitor-loop-error] {e}", file=sys.stderr, flush=True)
            traceback.print_exc()

        time.sleep(max(30, REPLICA_MONITOR_INTERVAL_SEC))


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


def kb_my_sub(connect_url: str, active_devices: int | None = None):
    devices_label = "📱 Мои устройства"
    if active_devices is not None:
        devices_label = f"📱 Мои устройства ({int(active_devices)}/{DEVICE_SOFT_LIMIT})"
    return {
        "inline_keyboard": [
            [{"text": "🔌 Подключиться", "url": connect_url}],
            [{"text": devices_label, "callback_data": CB_MY_DEVICES}],
            [{"text": "⬅️ Вернуться назад", "callback_data": CB_MAIN}],
        ]
    }


def kb_my_devices(vpn_name: str, rows: list[tuple]):
    buttons = []
    for idx, r in enumerate(rows, start=1):
        dkey = (r[0] or "")
        tok = device_action_token(vpn_name, dkey)
        ident = human_device_id(dkey, (r[1] or ""))
        ident_short = _safe_text(ident, 18)
        label = f"Отключить {ident_short} ({idx})"
        buttons.append([{"text": label[:62], "callback_data": f"{CB_MY_DEVICE_REVOKE_PREFIX}{tok}"}])
    buttons.append([{"text": "⬅️ Вернуться назад", "callback_data": CB_MY_SUB}])
    return {"inline_keyboard": buttons}


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
            [
                {"text": "📱 Устройства", "callback_data": CB_ADMIN_DEVICES},
                {"text": "🟢 Онлайн сессии", "callback_data": CB_ADMIN_ONLINE},
            ],
            [{"text": "📊 Трафик (24ч)", "callback_data": CB_ADMIN_TRAFFIC}],
            [
                {"text": "🔁 Рестарт UK", "callback_data": CB_ADMIN_RESTART_UK},
                {"text": "🔁 Рестарт TR", "callback_data": CB_ADMIN_RESTART_TR},
            ],
            [{"text": "🔄 Обновить", "callback_data": CB_ADMIN_DEVICES_REFRESH}],
            [{"text": "⬅️ Вернуться назад", "callback_data": CB_ADMIN}],
        ]
    }


def kb_admin_traffic():
    return {
        "inline_keyboard": [
            [
                {"text": "👤 Пользователь", "callback_data": CB_ADMIN_TRAFFIC_PICK},
                {"text": "🔄 Обновить", "callback_data": CB_ADMIN_TRAFFIC_REFRESH},
            ],
            [{"text": "⬅️ Вернуться назад", "callback_data": CB_ADMIN_SERVICE}],
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
            label = r.get("label") or f"{r['status']} {r['display']} | {r['exp_txt']}"
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
    try:
        ingest_device_log(conn)
    except Exception as e:
        print(f"[device-ingest-error] {e}", file=sys.stderr, flush=True)
    active_devices = count_active_devices(conn, vpn_name)
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
    send_message(chat_id, text, kb_my_sub(info["menu_url"], active_devices=active_devices), parse_mode="HTML")


def show_my_devices(conn: sqlite3.Connection, msg: dict):
    user = msg["from"]
    chat_id = msg["chat"]["id"]
    tg_id = int(user["id"])
    row = get_user(conn, tg_id)
    if not row:
        send_message(chat_id, "Подписка не найдена. Нажми /start", kb_main(is_admin=is_admin_user(user)))
        return
    vpn_name = row[2]
    try:
        ingest_device_log(conn)
    except Exception as e:
        print(f"[device-ingest-error] {e}", file=sys.stderr, flush=True)
    rows = get_devices_for_user(conn, vpn_name, limit=DEVICE_LIST_LIMIT)
    if not rows:
        send_message(
            chat_id,
            "📱 Устройства\n\nПока нет данных по устройствам.\nОбновите подписку в приложении и попробуйте снова.",
            kb_my_devices(vpn_name, []),
        )
        return
    active_count = sum(1 for r in rows if int((r[13] if len(r) > 13 else 0) or 0) == 0)
    lines = [
        "📱 Мои устройства:",
        f"Список устройств ({active_count}/{DEVICE_SOFT_LIMIT})",
    ]
    lines.append("")
    for i, r in enumerate(rows, start=1):
        device_key, hwid, ua, ip, platform, os_name, os_version, device_model, app_version, lang, first_seen, last_seen, hits, pending = r
        ident = human_device_id(device_key, hwid)
        title = human_device_title(platform, os_name, os_version, device_model, ua)
        name = title or f"Устройство {i}"
        lines.append(f"<b>{html.escape(_safe_text(name, 100))}</b>")
        lines.append(f"Дата подключения: {_fmt_ts(int(last_seen or 0))}")
        lines.append(f"User Agent: {html.escape(_safe_text(ua, 140))}")
        lines.append(f"HWID: {html.escape(_safe_text(ident, 40))}")
        if int(pending or 0) == 1:
            lines.append("Статус: ⏳ Ожидает активации (освободите слот)")
        lines.append("")
    send_message(chat_id, "\n".join(lines)[:3500], kb_my_devices(vpn_name, rows), parse_mode="HTML")


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


def show_admin_devices_overview(conn: sqlite3.Connection, msg: dict, force_live: bool = False):
    user = msg["from"]
    chat_id = msg["chat"]["id"]
    if not is_admin_user(user):
        send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
        return
    try:
        parsed = ingest_device_log(conn)
    except Exception as e:
        print(f"[device-ingest-error] {e}", file=sys.stderr, flush=True)
        parsed = 0
    rows = get_device_stats_by_user(conn, limit=12)
    online_total = online_users_count(conn)
    live = get_live_online_snapshot(force=force_live)
    live_users_raw = live.get("all_users") or set()
    live_users = set()
    for u in live_users_raw:
        live_users.add(u)
        live_users.add(canonical_vpn_name(conn, u))
    lines = [
        f"📱 Устройства (сбор без лимитов)",
        f"Обновлено записей: {parsed}",
        f"Онлайн сейчас (окно {int(ONLINE_WINDOW_SEC/60)} мин): {online_total}",
    ]
    if live.get("enabled"):
        lines.append(f"LIVE по трафику ({LIVE_ONLINE_SAMPLE_SEC}s): {len(live_users)}")
        node_lines = []
        for node_name, rec in (live.get("nodes") or {}).items():
            if rec.get("ok"):
                node_lines.append(f"{node_name}={len(rec.get('users') or set())}")
            else:
                node_lines.append(f"{node_name}=n/a")
        if node_lines:
            lines.append("Узлы: " + ", ".join(node_lines))
    if rows:
        lines.append("")
        lines.append("Топ пользователей по числу устройств:")
        for i, r in enumerate(rows, start=1):
            vpn_name = (r[0] or "").strip()
            disp = display_name_for(conn, vpn_name) or vpn_name
            if disp != vpn_name:
                who = f"{disp} ({vpn_name})"
            else:
                who = vpn_name
            last_seen = int(r[3] or 0)
            live_mark = " 🟢LIVE" if vpn_name in live_users else ""
            lines.append(
                f"{i}. {who} — активных {int(r[1] or 0)}, в ожидании {int(r[2] or 0)} "
                f"({online_label(last_seen)}, последняя активность: {_fmt_ts(last_seen)}){live_mark}"
            )
    else:
        lines.append("\nПока нет данных. Устройства появятся после запросов к /sub/*.")
    lines.append("\nВыбери пользователя через «🔎 Поиск», чтобы посмотреть детали.")
    send_message(chat_id, "\n".join(lines)[:3500], kb_admin_service())


def show_admin_online_sessions(conn: sqlite3.Connection, msg: dict, force_live: bool = False):
    user = msg["from"]
    chat_id = msg["chat"]["id"]
    if not is_admin_user(user):
        send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
        return
    try:
        ingest_device_log(conn)
    except Exception as e:
        print(f"[device-ingest-error] {e}", file=sys.stderr, flush=True)
    live = get_live_online_snapshot(force=force_live)
    if not live.get("enabled"):
        send_message(chat_id, "🟢 Онлайн сессии\n\nLIVE мониторинг отключен.", kb_admin_service())
        return

    lines = ["🟢 Онлайн сессии", f"Окно детекции: {LIVE_ONLINE_SAMPLE_SEC} сек", ""]
    total_live = len(live.get("all_users") or set())
    lines.append(f"Всего активных аккаунтов: {total_live}")

    nodes = live.get("nodes") or {}
    for node_name, rec in nodes.items():
        if not rec.get("ok"):
            lines.append(f"\n{node_name}: n/a")
            continue
        users = sorted(rec.get("users") or set())
        lines.append(f"\n{node_name}: {len(users)}")
        for uname in users[:20]:
            canon = canonical_vpn_name(conn, uname)
            disp = display_name_for(conn, canon) or canon
            who = f"{disp} ({canon})" if disp != canon else canon
            d = get_latest_device_for_user(conn, canon)
            if d:
                dkey, hwid, ua, platform, os_name, os_version, device_model, app_ver, _last_seen = d
                title = human_device_title(platform, os_name, os_version, device_model, ua) or "Устройство"
                ident = human_device_id(dkey, hwid)
                lines.append(f"- {who} | { _safe_text(title, 48) } | { _safe_text(ident, 24) }")
            else:
                lines.append(f"- {who} | устройство: n/a")
    send_message(chat_id, "\n".join(lines)[:3500], kb_admin_service())


def show_admin_traffic(conn: sqlite3.Connection, msg: dict, hours: int = 24):
    user = msg["from"]
    chat_id = msg["chat"]["id"]
    if not is_admin_user(user):
        send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
        return
    rows = get_traffic_top(conn, hours=hours, limit=15)
    lines = [f"📊 Трафик за {hours}ч"]
    if not rows:
        lines.append("")
        lines.append("Данных пока нет. Сбор трафика выполняется периодически.")
        send_message(chat_id, "\n".join(lines), kb_admin_traffic())
        return
    lines.append("")
    lines.append("Топ пользователей:")
    for i, r in enumerate(rows, start=1):
        name = r["vpn_name"]
        disp = display_name_for(conn, name) or name
        who = f"{disp} ({name})" if disp != name else name
        lines.append(
            f"{i}. {who} — ↓{_fmt_bytes(r['downlink'])} ↑{_fmt_bytes(r['uplink'])} Σ{_fmt_bytes(r['total'])}"
        )
    lines.append("")
    lines.append("Нажми «👤 Пользователь», чтобы открыть деталку.")
    send_message(chat_id, "\n".join(lines)[:3500], kb_admin_traffic())


def show_admin_user_traffic(conn: sqlite3.Connection, msg: dict, vpn_name: str, hours: int = 24):
    chat_id = msg["chat"]["id"]
    info = get_traffic_user_breakdown(conn, vpn_name, hours=hours)
    disp = display_name_for(conn, vpn_name) or vpn_name
    who = f"{disp} ({vpn_name})" if disp != vpn_name else vpn_name
    lines = [f"📊 Трафик пользователя {who}", f"Окно: {hours}ч", ""]
    lines.append(
        f"Итого: ↓{_fmt_bytes(info['downlink'])} ↑{_fmt_bytes(info['uplink'])} Σ{_fmt_bytes(info['total'])}"
    )
    lines.append(f"Последний срез: {_fmt_ts(int(info.get('last_ts') or 0))}")
    if info["nodes"]:
        lines.append("")
        lines.append("По узлам:")
        for r in info["nodes"]:
            lines.append(
                f"- {r['node']}: ↓{_fmt_bytes(r['downlink'])} ↑{_fmt_bytes(r['uplink'])} Σ{_fmt_bytes(r['total'])}"
            )
    else:
        lines.append("")
        lines.append("По узлам: данных нет.")
    send_message(chat_id, "\n".join(lines)[:3500], kb_admin_traffic())


def show_admin_user_devices(conn: sqlite3.Connection, msg: dict, vpn_name: str):
    chat_id = msg["chat"]["id"]
    try:
        ingest_device_log(conn)
    except Exception as e:
        print(f"[device-ingest-error] {e}", file=sys.stderr, flush=True)

    rows = get_devices_for_user(conn, vpn_name, limit=DEVICE_LIST_LIMIT)
    live = get_live_online_snapshot(force=False)
    live_users_raw = live.get("all_users") or set()
    live_users = set()
    for u in live_users_raw:
        live_users.add(u)
        live_users.add(canonical_vpn_name(conn, u))
    disp = display_name_for(conn, vpn_name) or vpn_name
    if disp != vpn_name:
        header_user = f"{disp} ({vpn_name})"
    else:
        header_user = vpn_name
    if not rows:
        send_message(chat_id, f"📱 Устройства пользователя {header_user}\n\nДанных пока нет.", kb_admin_service())
        return

    active_count = sum(1 for r in rows if int((r[13] if len(r) > 13 else 0) or 0) == 0)
    pending_count = sum(1 for r in rows if int((r[13] if len(r) > 13 else 0) or 0) == 1)
    lines = [
        f"📱 Устройства пользователя {header_user}",
        f"Показано: {len(rows)} (макс {DEVICE_LIST_LIMIT})",
        f"Активных: {active_count}/{DEVICE_SOFT_LIMIT}, в ожидании: {pending_count}",
        f"LIVE по трафику: {'🟢 онлайн' if vpn_name in live_users else '⚪ офлайн'}",
        "",
    ]
    for i, r in enumerate(rows, start=1):
        device_key, hwid, ua, ip, platform, os_name, os_version, device_model, app_version, lang, first_seen, last_seen, hits, pending = r
        ident = human_device_id(device_key, hwid)
        title = human_device_title(platform, os_name, os_version, device_model, ua)
        lines.append(f"{i}) ID: {_safe_text(ident, 48)}")
        if title:
            lines.append(f"Устройство: {_safe_text(title, 120)}")
        lines.append(f"Статус: {'⏳ Ожидает активации' if int(pending or 0) == 1 else '✅ Активно'}")
        lines.append(f"Дата подключения: {_fmt_ts(int(last_seen or 0))}")
        lines.append(f"Первый раз: {_fmt_ts(int(first_seen or 0))}")
        if ip:
            lines.append(f"IP: {ip}")
        if app_version:
            lines.append(f"App: {_safe_text(app_version, 60)}")
        if lang:
            lines.append(f"Lang: {_safe_text(lang, 30)}")
        lines.append(f"User Agent: {_safe_text(ua, 180)}")
        lines.append(f"Запросов: {int(hits or 0)}")
        lines.append("")
    send_message(chat_id, "\n".join(lines)[:3500], kb_admin_service())


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
    if intent == "devices":
        counts = get_device_counts_map(conn)
        for r in rows:
            n = r.get("name", "")
            active, pending = counts.get(n, (0, 0))
            r["devices_active"] = active
            r["devices_pending"] = pending
            suffix = f"{active}"
            if pending > 0:
                suffix += f" (+{pending})"
            r["label"] = f"{r['display']} | устройств: {suffix}"
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
    elif intent == "devices":
        title = "Устройства: выбери пользователя"
        can_choose = True
    elif intent == "traffic":
        title = "Трафик: выбери пользователя"
        can_choose = True
    else:
        title = "Удаление: выбери пользователя"
        can_choose = True

    q_txt = f"\nФильтр: {query}" if query else ""
    line_items = []
    for i, r in enumerate(page, start=offset + 1):
        if intent == "devices":
            active = int(r.get("devices_active") or 0)
            pending = int(r.get("devices_pending") or 0)
            suffix = f"{active}"
            if pending > 0:
                suffix += f" (+{pending})"
            line_items.append(f"{i}. {r['display']} | устройств: {suffix}")
        else:
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

    if step == STATE_RESTART_UK_CONFIRM and action == CB_CONFIRM_RESTART_UK:
        args = [REPLICA_OPS_CMD, "--node", "uk", "--action", "restart-post"]
        if MONITOR_CHECK_USER:
            args += ["--user", MONITOR_CHECK_USER]
        rc, out = run_cmd(args, timeout_sec=180)
        clear_admin_state(conn, tg_id)
        if rc == 0:
            send_message(chat_id, "✅ Реплика UK: xray перезапущен, post-check OK.", kb_admin_service())
        else:
            send_message(chat_id, f"❌ Реплика UK: ошибка restart/post-check.\n\n{(out or '')[:2000]}", kb_admin_service())
        return True

    if step == STATE_RESTART_TR_CONFIRM and action == CB_CONFIRM_RESTART_TR:
        args = [REPLICA_OPS_CMD, "--node", "tr", "--action", "restart-post"]
        if MONITOR_CHECK_USER:
            args += ["--user", MONITOR_CHECK_USER]
        rc, out = run_cmd(args, timeout_sec=180)
        clear_admin_state(conn, tg_id)
        if rc == 0:
            send_message(chat_id, "✅ Реплика TR: xray перезапущен, post-check OK.", kb_admin_service())
        else:
            send_message(chat_id, f"❌ Реплика TR: ошибка restart/post-check.\n\n{(out or '')[:2000]}", kb_admin_service())
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
        if intent == "devices":
            clear_admin_state(conn, tg_id)
            show_admin_user_devices(conn, msg, name)
            return True
        if intent == "traffic":
            clear_admin_state(conn, tg_id)
            show_admin_user_traffic(conn, msg, name, hours=24)
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
        CB_CONFIRM_RESTART_UK,
        CB_CONFIRM_RESTART_TR,
    ):
        if handle_confirm_callback(conn, msg, action, st):
            return

    if action in (CB_MAIN, "Вернутся назад", "⬅️ Вернутся назад", "Вернуться назад", "⬅️ Вернуться назад"):
        clear_admin_state(conn, tg_id)
        show_main(chat_id, user)
    elif action in (CB_MY_SUB, "Моя подписка", "👤 Моя подписка"):
        clear_admin_state(conn, tg_id)
        show_my_subscription(conn, msg)
    elif action == CB_MY_DEVICES:
        clear_admin_state(conn, tg_id)
        show_my_devices(conn, msg)
    elif action == CB_MY_DEVICE_REVOKE_ALL:
        clear_admin_state(conn, tg_id)
        row = get_user(conn, tg_id)
        if not row:
            send_message(chat_id, "Подписка не найдена. Нажми /start", kb_main(is_admin=is_admin_user(user)))
            return
        vpn_name = row[2]
        n, promoted = revoke_all_devices(conn, vpn_name)
        extra = f"\nАктивировано из ожидания: {promoted}" if promoted > 0 else ""
        send_message(chat_id, f"✅ Отвязано устройств: {n}{extra}", kb_main(is_admin=is_admin_user(user)))
    elif action.startswith(CB_MY_DEVICE_REVOKE_PREFIX):
        clear_admin_state(conn, tg_id)
        row = get_user(conn, tg_id)
        if not row:
            send_message(chat_id, "Подписка не найдена. Нажми /start", kb_main(is_admin=is_admin_user(user)))
            return
        vpn_name = row[2]
        token = action[len(CB_MY_DEVICE_REVOKE_PREFIX):].strip()
        ok, promoted = revoke_device_by_token(conn, vpn_name, token)
        if ok:
            extra = f"\nАктивировано из ожидания: {promoted}" if promoted > 0 else ""
            send_message(chat_id, f"✅ Устройство отвязано.{extra}", kb_main(is_admin=is_admin_user(user)))
        else:
            send_message(chat_id, "⚠️ Устройство не найдено или уже отвязано.", kb_main(is_admin=is_admin_user(user)))
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
    elif action == CB_ADMIN_DEVICES:
        if not is_admin_user(user):
            send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
            return
        try:
            ingest_device_log(conn)
        except Exception as e:
            print(f"[device-ingest-error] {e}", file=sys.stderr, flush=True)
        start_select(conn, msg, intent="devices", query="", offset=0)
    elif action == CB_ADMIN_DEVICES_REFRESH:
        if not is_admin_user(user):
            send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
            return
        clear_admin_state(conn, tg_id)
        try:
            ingest_device_log(conn)
        except Exception as e:
            print(f"[device-ingest-error] {e}", file=sys.stderr, flush=True)
        start_select(conn, msg, intent="devices", query="", offset=0)
    elif action == CB_ADMIN_ONLINE:
        if not is_admin_user(user):
            send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
            return
        clear_admin_state(conn, tg_id)
        show_admin_online_sessions(conn, msg, force_live=True)
    elif action == CB_ADMIN_TRAFFIC:
        if not is_admin_user(user):
            send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
            return
        clear_admin_state(conn, tg_id)
        show_admin_traffic(conn, msg, hours=24)
    elif action == CB_ADMIN_TRAFFIC_PICK:
        if not is_admin_user(user):
            send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
            return
        start_select(conn, msg, intent="traffic", query="", offset=0)
    elif action == CB_ADMIN_TRAFFIC_REFRESH:
        if not is_admin_user(user):
            send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
            return
        clear_admin_state(conn, tg_id)
        show_admin_traffic(conn, msg, hours=24)
    elif action == CB_ADMIN_RESTART_UK:
        if not is_admin_user(user):
            send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
            return
        set_admin_state(conn, tg_id, STATE_RESTART_UK_CONFIRM, {})
        send_message(chat_id, "Подтвердить мягкий рестарт xray на реплике UK и post-check?", kb_confirm(CB_CONFIRM_RESTART_UK))
    elif action == CB_ADMIN_RESTART_TR:
        if not is_admin_user(user):
            send_message(chat_id, "Эта команда только для администратора.", kb_main(is_admin=False))
            return
        set_admin_state(conn, tg_id, STATE_RESTART_TR_CONFIRM, {})
        send_message(chat_id, "Подтвердить мягкий рестарт xray на реплике TR и post-check?", kb_confirm(CB_CONFIRM_RESTART_TR))
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
    replica_monitor = Thread(target=replica_monitor_loop, daemon=True)
    replica_monitor.start()
    trial_notifier = Thread(target=trial_notice_loop, daemon=True)
    trial_notifier.start()
    traffic_collector = Thread(target=traffic_collect_loop, daemon=True)
    traffic_collector.start()

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
