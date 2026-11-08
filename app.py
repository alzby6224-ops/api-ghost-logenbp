import asyncio
import os
import threading
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
from xCoRe import loginbp, GhosTCMD

PORT = int(os.environ.get('PORT', 10000))
API_KEY = "xAlInAs"
GHOST_ACCOUNT_COUNT = 3

app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------------------------
# Account pool with rotation + busy locking
# ---------------------------------------------------------------------------

class AccountPool:
    """
    Dynamic account pool — size = whatever is in accs.txt (3, 50, 100, 150, ...).
    No fixed limit.
    Each /ghost request acquires up to 3 FREE accounts starting from a rotating cursor.
    Busy accounts are skipped; if only last accounts are free, those are used.
    When the end is reached, cursor wraps to the beginning.
    Accounts are released when the request finishes (or after busy_ttl seconds).
    """

    def __init__(self, path=None, busy_ttl=90):
        self._lock = threading.Lock()
        self._accounts = []          # list[(uid, pw)]
        self._busy_until = {}        # uid -> monotonic deadline
        self._cursor = 0             # rotation cursor
        self._busy_ttl = float(busy_ttl)
        self._path = path or self._default_path()
        self.reload()

    @staticmethod
    def _default_path():
        base = os.path.dirname(os.path.abspath(__file__))
        p = os.path.join(base, "accs.txt")
        return p if os.path.exists(p) else "accs.txt"

    def reload(self):
        accounts = []
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and ":" in line:
                            uid, pw = line.split(":", 1)
                            uid, pw = uid.strip(), pw.strip()
                            if uid and pw:
                                accounts.append((uid, pw))
        except Exception as e:
            print(f"[POOL] load error: {e}")
        with self._lock:
            self._accounts = accounts
            # drop busy entries for removed uids
            valid = {u for u, _ in accounts}
            self._busy_until = {u: t for u, t in self._busy_until.items() if u in valid}
            if self._cursor >= len(self._accounts):
                self._cursor = 0
        print(f"[POOL] loaded {len(accounts)} accounts from {self._path}")
        return len(accounts)

    def size(self):
        with self._lock:
            return len(self._accounts)

    def _is_busy(self, uid, now):
        until = self._busy_until.get(uid, 0)
        return until > now

    def acquire(self, count=GHOST_ACCOUNT_COUNT):
        """
        Acquire up to `count` free accounts starting from cursor, wrapping around.
        Marks them busy. Returns list[(uid, pw)] (may be shorter if not enough free).
        """
        with self._lock:
            n = len(self._accounts)
            if n == 0:
                return []
            now = time.monotonic()
            # cleanup expired busy flags
            expired = [u for u, t in self._busy_until.items() if t <= now]
            for u in expired:
                self._busy_until.pop(u, None)

            picked = []
            start = self._cursor % n
            # scan full circle once
            for i in range(n):
                idx = (start + i) % n
                uid, pw = self._accounts[idx]
                if self._is_busy(uid, now):
                    continue
                picked.append((uid, pw))
                self._busy_until[uid] = now + self._busy_ttl
                if len(picked) >= count:
                    # advance cursor past last picked for fair rotation
                    self._cursor = (idx + 1) % n
                    break
            else:
                # acquired fewer than count; still advance a bit
                self._cursor = (start + max(1, len(picked))) % n

            free_left = sum(1 for u, _ in self._accounts if not self._is_busy(u, now) and u not in {x[0] for x in picked})
            print(
                f"[POOL] acquire {len(picked)}/{count} "
                f"uids={[u for u, _ in picked]} cursor={self._cursor} free≈{free_left}"
            )
            return picked

    def release(self, uids):
        """Release accounts early (optional) after job finishes."""
        with self._lock:
            for uid in uids:
                self._busy_until.pop(str(uid), None)
            print(f"[POOL] released {list(uids)}")


account_pool = AccountPool(busy_ttl=90)

# ---------------------------------------------------------------------------
# Ghost workers
# ---------------------------------------------------------------------------

async def _login_and_ghost(uid, pw, teamcode, name):
    try:
        print(f"[API] login attempt uid={uid}")
        login_data = await loginbp(uid, pw, "ME")
        if not login_data:
            print(f"[API] login FAILED uid={uid}")
            return uid, False, "login_failed"
        print(
            f"[API] login OK uid={login_data.get('bot_uid')} "
            f"name={login_data.get('account_name')} "
            f"chat={login_data.get('chat_ip')}:{login_data.get('chat_port')}"
        )
        ok = await GhosTCMD(teamcode, name, login_data)
        print(f"[API] ghost uid={uid} bot={login_data.get('bot_uid')} result={ok}")
        return uid, bool(ok), "ok" if ok else "no_team_data"
    except Exception as e:
        print(f"[API] uid={uid} exception: {e}")
        return uid, False, str(e)


class SimpleAPI:
    def __init__(self):
        self.running = True

    def FlInApKy(self, api_key):
        return api_key == API_KEY

    def xSendGhost(self, teamcode, name):
        try:
            if account_pool.size() == 0:
                account_pool.reload()
            if account_pool.size() == 0:
                return {
                    "status": "error",
                    "message": "لا يوجد حساب في accs.txt",
                    "الحالة": "خطأ",
                    "sent": 0,
                    "requested": GHOST_ACCOUNT_COUNT,
                }

            batch = account_pool.acquire(GHOST_ACCOUNT_COUNT)
            if not batch:
                return {
                    "status": "error",
                    "message": "كل الحسابات مشغولة حالياً - حاول بعد ثوانٍ",
                    "الحالة": "خطأ",
                    "sent": 0,
                    "requested": GHOST_ACCOUNT_COUNT,
                    "pool_size": account_pool.size(),
                }

            acquired_uids = [u for u, _ in batch]
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                tasks = [_login_and_ghost(uid, pw, teamcode, name) for uid, pw in batch]
                results = loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            finally:
                loop.close()
                # free accounts so next squad can reuse sooner than TTL
                account_pool.release(acquired_uids)

            sent = 0
            details = []
            for item in results:
                if isinstance(item, Exception):
                    details.append({"error": str(item), "ok": False})
                    continue
                uid, ok, detail = item
                details.append({"uid": uid, "ok": ok, "detail": detail})
                if ok:
                    sent += 1

            if sent > 0:
                return {
                    "status": "success",
                    "message": f"تم إرسال {sent} Ghost بنجاح",
                    "الحالة": "نجاح",
                    "sent": sent,
                    "requested": len(batch),
                    "accounts_used": acquired_uids,
                    "details": details,
                }
            return {
                "status": "error",
                "message": "فشل إرسال الـ Ghost - لم يتم استخراج بيانات الفريق",
                "الحالة": "خطأ",
                "sent": 0,
                "requested": len(batch),
                "accounts_used": acquired_uids,
                "details": details,
            }
        except Exception as e:
            print(f"[API] exception: {e}")
            return {
                "status": "error",
                "message": f"خطأ: {str(e)}",
                "الحالة": "خطأ",
                "sent": 0,
            }


api_handler = SimpleAPI()


@app.route('/')
def home():
    return jsonify({
        "status": "success",
        "message": "DoNe By xAllnAs Tg : @xAllnAs",
        "endpoints": ["/ghost?teamcode=CODE&name=NAME&api_key=KEY"],
        "ghosts_per_request": GHOST_ACCOUNT_COUNT,
        "pool_size": account_pool.size(),
    })


@app.route('/ghost')
def ghost():
    teamcode = request.args.get('teamcode')
    name = request.args.get('name')
    api_key = request.args.get('api_key')

    if not api_key:
        return jsonify({"status": "error", "message": "Error In Api KeY", "الحالة": "خطأ"}), 401

    if not api_handler.FlInApKy(api_key):
        return jsonify({"status": "error", "message": "Error In Api KeY", "الحالة": "خطأ"}), 401

    if not teamcode or not name:
        return jsonify({
            "status": "error",
            "message": "لازم تدخل teamcode و name",
            "الحالة": "خطأ"
        }), 400

    result = api_handler.xSendGhost(teamcode, name)
    return jsonify(result)


@app.route('/healthz')
def healthz():
    return {
        'status': 'ok',
        'pool_size': account_pool.size(),
    }, 200


@app.route('/reload_accounts')
def reload_accounts():
    api_key = request.args.get('api_key')
    if not api_key or not api_handler.FlInApKy(api_key):
        return jsonify({"status": "error", "message": "Error In Api KeY"}), 401
    n = account_pool.reload()
    return jsonify({"status": "success", "loaded": n})


def run_web():
    account_pool.reload()
    app.run(host='0.0.0.0', port=PORT, use_reloader=False, threaded=True)


if __name__ == '__main__':
    run_web()
