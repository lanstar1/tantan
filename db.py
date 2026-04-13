"""
Persistence Layer - PostgreSQL (Render) / In-memory fallback (local)
"""
import os, json
from datetime import datetime

DB_URL = os.environ.get("DATABASE_URL", "")

# ═══════════════════════════════════════════════════════════════════
# PostgreSQL mode
# ═══════════════════════════════════════════════════════════════════
if DB_URL:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    def _conn():
        url = DB_URL.replace("postgres://", "postgresql://", 1)
        return psycopg2.connect(url, cursor_factory=RealDictCursor)

    def init_db():
        with _conn() as c:
            cur = c.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'teacher',
                display_name TEXT,
                classin_uid TEXT DEFAULT '',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY DEFAULT 1,
                sid TEXT, secret TEXT
            )""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS classin_users (
                uid TEXT PRIMARY KEY,
                telephone TEXT, nickname TEXT,
                role TEXT, status TEXT DEFAULT 'active'
            )""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS courses (
                course_id TEXT PRIMARY KEY,
                name TEXT, teacher_uid TEXT DEFAULT ''
            )""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS classes (
                class_id TEXT PRIMARY KEY,
                course_id TEXT, name TEXT,
                begin_time BIGINT, end_time BIGINT,
                teacher_uid TEXT
            )""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS webhooks (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ DEFAULT NOW(),
                cmd TEXT, sid TEXT, data JSONB
            )""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS feedbacks (
                id SERIAL PRIMARY KEY,
                course_id TEXT, class_id TEXT,
                teacher_uid TEXT, student_uid TEXT,
                comment TEXT, created_at TIMESTAMPTZ DEFAULT NOW()
            )""")
            c.commit()

    # ── Credentials ─────────────────────────────────
    def get_creds():
        with _conn() as c:
            cur = c.cursor()
            cur.execute("SELECT sid, secret FROM credentials WHERE id=1")
            r = cur.fetchone()
            return (r["sid"], r["secret"]) if r else (None, None)

    def set_creds(sid, secret):
        with _conn() as c:
            cur = c.cursor()
            cur.execute("""INSERT INTO credentials (id,sid,secret) VALUES (1,%s,%s)
                           ON CONFLICT (id) DO UPDATE SET sid=%s, secret=%s""",
                        (sid, secret, sid, secret))
            c.commit()

    # ── Accounts ────────────────────────────────────
    def get_account(username):
        with _conn() as c:
            cur = c.cursor()
            cur.execute("SELECT * FROM accounts WHERE username=%s", (username,))
            r = cur.fetchone()
            if r: return {"username": r["username"], "password_hash": r["password_hash"],
                          "role": r["role"], "displayName": r["display_name"],
                          "classInUid": r["classin_uid"] or "", "created": str(r["created_at"])}
            return None

    def set_account(username, pw_hash, role, display_name, classin_uid=""):
        with _conn() as c:
            cur = c.cursor()
            cur.execute("""INSERT INTO accounts (username,password_hash,role,display_name,classin_uid)
                           VALUES (%s,%s,%s,%s,%s)
                           ON CONFLICT (username) DO UPDATE SET password_hash=%s,role=%s,display_name=%s,classin_uid=%s""",
                        (username, pw_hash, role, display_name, classin_uid,
                         pw_hash, role, display_name, classin_uid))
            c.commit()

    def del_account(username):
        with _conn() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM accounts WHERE username=%s", (username,))
            c.commit()

    def list_accounts():
        with _conn() as c:
            cur = c.cursor()
            cur.execute("SELECT * FROM accounts ORDER BY created_at")
            return [{"username": r["username"], "role": r["role"],
                     "displayName": r["display_name"], "classInUid": r["classin_uid"] or "",
                     "created": str(r["created_at"])} for r in cur.fetchall()]

    def has_admin():
        with _conn() as c:
            cur = c.cursor()
            cur.execute("SELECT 1 FROM accounts WHERE role='admin' LIMIT 1")
            return cur.fetchone() is not None

    # ── ClassIn Users ───────────────────────────────
    def set_user(uid, telephone, nickname, role):
        with _conn() as c:
            cur = c.cursor()
            cur.execute("""INSERT INTO classin_users (uid,telephone,nickname,role)
                           VALUES (%s,%s,%s,%s) ON CONFLICT (uid) DO UPDATE SET nickname=%s""",
                        (uid, telephone, nickname, role, nickname))
            c.commit()

    def list_users(role=None):
        with _conn() as c:
            cur = c.cursor()
            if role:
                cur.execute("SELECT * FROM classin_users WHERE role=%s", (role,))
            else:
                cur.execute("SELECT * FROM classin_users")
            return [dict(r) for r in cur.fetchall()]

    # ── Courses ─────────────────────────────────────
    def set_course(course_id, name, teacher_uid=""):
        with _conn() as c:
            cur = c.cursor()
            cur.execute("""INSERT INTO courses (course_id,name,teacher_uid)
                           VALUES (%s,%s,%s) ON CONFLICT (course_id) DO UPDATE SET name=%s""",
                        (course_id, name, teacher_uid, name))
            c.commit()

    def list_courses(teacher_uid=None):
        with _conn() as c:
            cur = c.cursor()
            if teacher_uid:
                cur.execute("SELECT * FROM courses WHERE teacher_uid=%s", (teacher_uid,))
            else:
                cur.execute("SELECT * FROM courses")
            return [{"courseId": r["course_id"], "name": r["name"],
                     "teacherUid": r["teacher_uid"]} for r in cur.fetchall()]

    # ── Classes ─────────────────────────────────────
    def set_class(class_id, course_id, name, begin, end, teacher_uid):
        with _conn() as c:
            cur = c.cursor()
            cur.execute("""INSERT INTO classes (class_id,course_id,name,begin_time,end_time,teacher_uid)
                           VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (class_id) DO UPDATE SET name=%s""",
                        (class_id, course_id, name, begin, end, teacher_uid, name))
            c.commit()

    def del_class(class_id):
        with _conn() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM classes WHERE class_id=%s", (class_id,))
            c.commit()

    def list_classes(course_id=None, teacher_uid=None):
        with _conn() as c:
            cur = c.cursor()
            q = "SELECT * FROM classes WHERE 1=1"
            params = []
            if course_id: q += " AND course_id=%s"; params.append(course_id)
            if teacher_uid: q += " AND teacher_uid=%s"; params.append(teacher_uid)
            cur.execute(q, params)
            return [{"classId": r["class_id"], "courseId": r["course_id"], "name": r["name"],
                     "begin": r["begin_time"], "end": r["end_time"],
                     "teacherUid": r["teacher_uid"]} for r in cur.fetchall()]

    # ── Webhooks ────────────────────────────────────
    def add_webhook(cmd, sid, data):
        with _conn() as c:
            cur = c.cursor()
            cur.execute("INSERT INTO webhooks (cmd,sid,data) VALUES (%s,%s,%s)",
                        (cmd, str(sid), json.dumps(data)))
            c.commit()

    def list_webhooks(limit=50):
        with _conn() as c:
            cur = c.cursor()
            cur.execute("SELECT * FROM webhooks ORDER BY id DESC LIMIT %s", (limit,))
            rows = cur.fetchall()
            cur.execute("SELECT COUNT(*) as cnt FROM webhooks")
            total = cur.fetchone()["cnt"]
            return [{"timestamp": str(r["timestamp"]), "cmd": r["cmd"],
                     "sid": r["sid"], "data": r["data"]} for r in rows], total

    # ── Feedbacks ───────────────────────────────────
    def add_feedback(course_id, class_id, teacher_uid, student_uid, comment):
        with _conn() as c:
            cur = c.cursor()
            cur.execute("""INSERT INTO feedbacks (course_id,class_id,teacher_uid,student_uid,comment)
                           VALUES (%s,%s,%s,%s,%s)""",
                        (course_id, class_id, teacher_uid, student_uid, comment))
            c.commit()

    def list_feedbacks(teacher_uid=None):
        with _conn() as c:
            cur = c.cursor()
            if teacher_uid:
                cur.execute("SELECT * FROM feedbacks WHERE teacher_uid=%s ORDER BY created_at DESC", (teacher_uid,))
            else:
                cur.execute("SELECT * FROM feedbacks ORDER BY created_at DESC")
            return [{"courseId": r["course_id"], "classId": r["class_id"],
                     "teacherUid": r["teacher_uid"], "studentUid": r["student_uid"],
                     "comment": r["comment"], "date": str(r["created_at"])} for r in cur.fetchall()]

    def count_all():
        with _conn() as c:
            cur = c.cursor()
            counts = {}
            for t, col in [("classin_users","role='teacher'"), ("classin_users","role='student'"),
                           ("courses","1=1"), ("classes","1=1"), ("webhooks","1=1"), ("feedbacks","1=1")]:
                cur.execute(f"SELECT COUNT(*) as cnt FROM {t} WHERE {col}")
                counts[t + col] = cur.fetchone()["cnt"]
            return {
                "teachers": counts["classin_usersrole='teacher'"],
                "students": counts["classin_usersrole='student'"],
                "courses": counts["courses1=1"], "classes": counts["classes1=1"],
                "webhooks": counts["webhooks1=1"], "feedbacks": counts["feedbacks1=1"],
            }

    print("[DB] PostgreSQL connected")

# ═══════════════════════════════════════════════════════════════════
# In-memory fallback (local dev)
# ═══════════════════════════════════════════════════════════════════
else:
    _accounts = {}
    _creds_store = {"sid": None, "secret": None}
    _users = {}
    _courses = {}
    _classes = {}
    _webhooks = []
    _feedbacks = []

    def init_db(): pass

    def get_creds(): return _creds_store["sid"], _creds_store["secret"]
    def set_creds(sid, secret): _creds_store["sid"] = sid; _creds_store["secret"] = secret

    def get_account(username): return _accounts.get(username)
    def set_account(username, pw_hash, role, display_name, classin_uid=""):
        _accounts[username] = {"username": username, "password_hash": pw_hash, "role": role,
                               "displayName": display_name, "classInUid": classin_uid,
                               "created": datetime.now().isoformat()}
    def del_account(username): _accounts.pop(username, None)
    def list_accounts(): return [{k:v for k,v in a.items() if k!="password_hash"} for a in _accounts.values()]
    def has_admin(): return any(a["role"]=="admin" for a in _accounts.values())

    def set_user(uid, telephone, nickname, role):
        _users[uid] = {"uid": uid, "telephone": telephone, "nickname": nickname, "role": role, "status": "active"}
    def list_users(role=None):
        u = list(_users.values())
        return [x for x in u if x["role"]==role] if role else u

    def set_course(cid, name, tuid=""): _courses[cid] = {"courseId": cid, "name": name, "teacherUid": tuid}
    def list_courses(teacher_uid=None):
        c = list(_courses.values())
        return [x for x in c if x["teacherUid"]==teacher_uid] if teacher_uid else c

    def set_class(clid, coid, name, begin, end, tuid):
        _classes[clid] = {"classId": clid, "courseId": coid, "name": name, "begin": begin, "end": end, "teacherUid": tuid}
    def del_class(clid): _classes.pop(clid, None)
    def list_classes(course_id=None, teacher_uid=None):
        c = list(_classes.values())
        if course_id: c = [x for x in c if x["courseId"]==course_id]
        if teacher_uid: c = [x for x in c if x["teacherUid"]==teacher_uid]
        return c

    def add_webhook(cmd, sid, data):
        _webhooks.append({"timestamp": datetime.now().isoformat(), "cmd": cmd, "sid": sid, "data": data})
        if len(_webhooks) > 500: _webhooks[:] = _webhooks[-500:]
    def list_webhooks(limit=50): return _webhooks[-limit:], len(_webhooks)

    def add_feedback(coid, clid, tuid, suid, comment):
        _feedbacks.append({"courseId": coid, "classId": clid, "teacherUid": tuid,
                           "studentUid": suid, "comment": comment, "date": datetime.now().isoformat()})
    def list_feedbacks(teacher_uid=None):
        f = _feedbacks
        return [x for x in f if x["teacherUid"]==teacher_uid] if teacher_uid else f

    def count_all():
        return {
            "teachers": len([u for u in _users.values() if u["role"]=="teacher"]),
            "students": len([u for u in _users.values() if u["role"]=="student"]),
            "courses": len(_courses), "classes": len(_classes),
            "webhooks": len(_webhooks), "feedbacks": len(_feedbacks),
        }

    print("[DB] In-memory mode (local dev)")
