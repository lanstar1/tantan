"""DB Layer v3 - PostgreSQL / In-memory dual mode"""
import os, json
from datetime import datetime, timedelta

DB_URL = os.environ.get("DATABASE_URL", "")
SESSION_EXPIRY_DAYS = 365  # 1 year

if DB_URL:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    def _conn():
        return psycopg2.connect(DB_URL.replace("postgres://","postgresql://",1), cursor_factory=RealDictCursor)

    def init_db():
        with _conn() as c:
            cur = c.cursor()
            cur.execute("""CREATE TABLE IF NOT EXISTS accounts (
                username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT DEFAULT 'teacher',
                display_name TEXT, classin_uid TEXT DEFAULT '', timezone TEXT DEFAULT 'Asia/Seoul',
                created_at TIMESTAMPTZ DEFAULT NOW())""")
            cur.execute("""CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY, username TEXT, role TEXT, classin_uid TEXT DEFAULT '',
                display_name TEXT, timezone TEXT DEFAULT 'Asia/Seoul',
                expires_at TIMESTAMPTZ, created_at TIMESTAMPTZ DEFAULT NOW())""")
            cur.execute("""CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY DEFAULT 1, sid TEXT, secret TEXT)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS classin_users (
                uid TEXT PRIMARY KEY, telephone TEXT, nickname TEXT, role TEXT, status TEXT DEFAULT 'active')""")
            cur.execute("""CREATE TABLE IF NOT EXISTS student_profiles (
                uid TEXT PRIMARY KEY, topik_level TEXT DEFAULT '', purpose TEXT DEFAULT '',
                notes TEXT DEFAULT '', native_lang TEXT DEFAULT '')""")
            cur.execute("""CREATE TABLE IF NOT EXISTS courses (
                course_id TEXT PRIMARY KEY, name TEXT, teacher_uid TEXT DEFAULT '')""")
            cur.execute("""CREATE TABLE IF NOT EXISTS classes (
                class_id TEXT PRIMARY KEY, course_id TEXT, name TEXT,
                begin_time BIGINT, end_time BIGINT, teacher_uid TEXT)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS webhooks (
                id SERIAL PRIMARY KEY, timestamp TIMESTAMPTZ DEFAULT NOW(),
                cmd TEXT, sid TEXT, data JSONB)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS feedbacks (
                id SERIAL PRIMARY KEY, course_id TEXT, class_id TEXT,
                teacher_uid TEXT, student_uid TEXT, comment TEXT, created_at TIMESTAMPTZ DEFAULT NOW())""")
            c.commit()

    # Credentials
    def get_creds():
        with _conn() as c:
            cur = c.cursor(); cur.execute("SELECT sid,secret FROM credentials WHERE id=1")
            r = cur.fetchone(); return (r["sid"],r["secret"]) if r else (None,None)
    def set_creds(sid, secret):
        with _conn() as c:
            c.cursor().execute("INSERT INTO credentials(id,sid,secret)VALUES(1,%s,%s)ON CONFLICT(id)DO UPDATE SET sid=%s,secret=%s",(sid,secret,sid,secret)); c.commit()

    # Accounts
    def get_account(username):
        with _conn() as c:
            cur = c.cursor(); cur.execute("SELECT * FROM accounts WHERE username=%s",(username,))
            r = cur.fetchone()
            if r: return {"username":r["username"],"password_hash":r["password_hash"],"role":r["role"],
                          "displayName":r["display_name"],"classInUid":r["classin_uid"] or "","timezone":r.get("timezone","Asia/Seoul"),
                          "created":str(r["created_at"])}
            return None
    def set_account(username, pw_hash, role, display_name, classin_uid="", timezone="Asia/Seoul"):
        with _conn() as c:
            c.cursor().execute("""INSERT INTO accounts(username,password_hash,role,display_name,classin_uid,timezone)
                VALUES(%s,%s,%s,%s,%s,%s)ON CONFLICT(username)DO UPDATE SET password_hash=%s,role=%s,display_name=%s,classin_uid=%s,timezone=%s""",
                (username,pw_hash,role,display_name,classin_uid,timezone,pw_hash,role,display_name,classin_uid,timezone)); c.commit()
    def update_password(username, pw_hash):
        with _conn() as c:
            c.cursor().execute("UPDATE accounts SET password_hash=%s WHERE username=%s",(pw_hash,username)); c.commit()
    def del_account(username):
        with _conn() as c:
            cur=c.cursor(); cur.execute("DELETE FROM accounts WHERE username=%s",(username,))
            cur.execute("DELETE FROM sessions WHERE username=%s",(username,)); c.commit()
    def list_accounts():
        with _conn() as c:
            cur=c.cursor(); cur.execute("SELECT * FROM accounts ORDER BY created_at")
            return [{"username":r["username"],"role":r["role"],"displayName":r["display_name"],
                     "classInUid":r["classin_uid"] or "","timezone":r.get("timezone","Asia/Seoul"),
                     "created":str(r["created_at"])} for r in cur.fetchall()]
    def has_admin():
        with _conn() as c:
            cur=c.cursor(); cur.execute("SELECT 1 FROM accounts WHERE role='admin' LIMIT 1"); return cur.fetchone() is not None

    # Sessions (DB-backed)
    def create_session(token, username, role, classin_uid, display_name, timezone="Asia/Seoul"):
        exp = datetime.utcnow() + timedelta(days=SESSION_EXPIRY_DAYS)
        with _conn() as c:
            c.cursor().execute("INSERT INTO sessions(token,username,role,classin_uid,display_name,timezone,expires_at)VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (token,username,role,classin_uid,display_name,timezone,exp)); c.commit()
    def get_session(token):
        with _conn() as c:
            cur=c.cursor(); cur.execute("SELECT * FROM sessions WHERE token=%s AND expires_at>NOW()",(token,))
            r=cur.fetchone()
            if r: return {"username":r["username"],"role":r["role"],"classInUid":r["classin_uid"] or "",
                          "displayName":r["display_name"],"timezone":r.get("timezone","Asia/Seoul")}
            return None
    def delete_session(token):
        with _conn() as c:
            c.cursor().execute("DELETE FROM sessions WHERE token=%s",(token,)); c.commit()
    def delete_user_sessions(username):
        with _conn() as c:
            c.cursor().execute("DELETE FROM sessions WHERE username=%s",(username,)); c.commit()

    # ClassIn Users
    def set_user(uid, telephone, nickname, role):
        with _conn() as c:
            c.cursor().execute("INSERT INTO classin_users(uid,telephone,nickname,role)VALUES(%s,%s,%s,%s)ON CONFLICT(uid)DO UPDATE SET nickname=%s",
                (uid,telephone,nickname,role,nickname)); c.commit()
    def list_users(role=None, search="", page=1, per_page=50):
        with _conn() as c:
            cur=c.cursor(); q="SELECT * FROM classin_users WHERE 1=1"; p=[]
            if role: q+=" AND role=%s"; p.append(role)
            if search: q+=" AND (nickname ILIKE %s OR telephone ILIKE %s)"; p+=[f"%{search}%",f"%{search}%"]
            cur.execute(q+" ORDER BY uid", p)
            all_rows = cur.fetchall()
            total = len(all_rows)
            start = (page-1)*per_page
            return [dict(r) for r in all_rows[start:start+per_page]], total

    # Student Profiles
    def get_student_profile(uid):
        with _conn() as c:
            cur=c.cursor(); cur.execute("SELECT * FROM student_profiles WHERE uid=%s",(uid,))
            r=cur.fetchone(); return dict(r) if r else {"uid":uid,"topik_level":"","purpose":"","notes":"","native_lang":""}
    def set_student_profile(uid, topik="", purpose="", notes="", native_lang=""):
        with _conn() as c:
            c.cursor().execute("""INSERT INTO student_profiles(uid,topik_level,purpose,notes,native_lang)
                VALUES(%s,%s,%s,%s,%s)ON CONFLICT(uid)DO UPDATE SET topik_level=%s,purpose=%s,notes=%s,native_lang=%s""",
                (uid,topik,purpose,notes,native_lang,topik,purpose,notes,native_lang)); c.commit()

    # Courses
    def set_course(cid, name, tuid=""):
        with _conn() as c:
            c.cursor().execute("INSERT INTO courses(course_id,name,teacher_uid)VALUES(%s,%s,%s)ON CONFLICT(course_id)DO UPDATE SET name=%s",
                (cid,name,tuid,name)); c.commit()
    def list_courses(teacher_uid=None):
        with _conn() as c:
            cur=c.cursor()
            if teacher_uid: cur.execute("SELECT * FROM courses WHERE teacher_uid=%s",(teacher_uid,))
            else: cur.execute("SELECT * FROM courses")
            return [{"courseId":r["course_id"],"name":r["name"],"teacherUid":r["teacher_uid"]} for r in cur.fetchall()]

    # Classes
    def set_class(clid, coid, name, begin, end, tuid):
        with _conn() as c:
            c.cursor().execute("INSERT INTO classes(class_id,course_id,name,begin_time,end_time,teacher_uid)VALUES(%s,%s,%s,%s,%s,%s)ON CONFLICT(class_id)DO UPDATE SET name=%s",
                (clid,coid,name,begin,end,tuid,name)); c.commit()
    def del_class(clid):
        with _conn() as c:
            c.cursor().execute("DELETE FROM classes WHERE class_id=%s",(clid,)); c.commit()
    def list_classes(course_id=None, teacher_uid=None):
        with _conn() as c:
            cur=c.cursor(); q="SELECT * FROM classes WHERE 1=1"; p=[]
            if course_id: q+=" AND course_id=%s"; p.append(course_id)
            if teacher_uid: q+=" AND teacher_uid=%s"; p.append(teacher_uid)
            cur.execute(q+" ORDER BY begin_time", p)
            return [{"classId":r["class_id"],"courseId":r["course_id"],"name":r["name"],
                     "begin":r["begin_time"],"end":r["end_time"],"teacherUid":r["teacher_uid"]} for r in cur.fetchall()]

    # Webhooks
    def add_webhook(cmd, sid, data):
        with _conn() as c:
            c.cursor().execute("INSERT INTO webhooks(cmd,sid,data)VALUES(%s,%s,%s)",(cmd,str(sid),json.dumps(data))); c.commit()
    def list_webhooks(limit=50):
        with _conn() as c:
            cur=c.cursor(); cur.execute("SELECT * FROM webhooks ORDER BY id DESC LIMIT %s",(limit,))
            rows=cur.fetchall(); cur.execute("SELECT COUNT(*) as cnt FROM webhooks"); total=cur.fetchone()["cnt"]
            return [{"timestamp":str(r["timestamp"]),"cmd":r["cmd"],"sid":r["sid"]} for r in rows], total
    def get_webhook_stats():
        with _conn() as c:
            cur=c.cursor()
            cur.execute("SELECT cmd, COUNT(*) as cnt FROM webhooks GROUP BY cmd ORDER BY cnt DESC")
            return [dict(r) for r in cur.fetchall()]

    # Feedbacks
    def add_feedback(coid, clid, tuid, suid, comment):
        with _conn() as c:
            c.cursor().execute("INSERT INTO feedbacks(course_id,class_id,teacher_uid,student_uid,comment)VALUES(%s,%s,%s,%s,%s)",
                (coid,clid,tuid,suid,comment)); c.commit()
    def list_feedbacks(teacher_uid=None):
        with _conn() as c:
            cur=c.cursor()
            if teacher_uid: cur.execute("SELECT * FROM feedbacks WHERE teacher_uid=%s ORDER BY created_at DESC",(teacher_uid,))
            else: cur.execute("SELECT * FROM feedbacks ORDER BY created_at DESC")
            return [{"courseId":r["course_id"],"classId":r["class_id"],"teacherUid":r["teacher_uid"],
                     "studentUid":r["student_uid"],"comment":r["comment"],"date":str(r["created_at"])} for r in cur.fetchall()]

    def count_all():
        with _conn() as c:
            cur=c.cursor(); d={}
            for t,w in [("classin_users","role='teacher'"),("classin_users","role='student'"),("courses","1=1"),("classes","1=1"),("webhooks","1=1"),("feedbacks","1=1")]:
                cur.execute(f"SELECT COUNT(*) as cnt FROM {t} WHERE {w}"); d[t+w]=cur.fetchone()["cnt"]
            return {"teachers":d["classin_usersrole='teacher'"],"students":d["classin_usersrole='student'"],
                    "courses":d["courses1=1"],"classes":d["classes1=1"],"webhooks":d["webhooks1=1"],"feedbacks":d["feedbacks1=1"]}
    print("[DB] PostgreSQL connected")

else:
    # ── In-memory fallback ──
    _accounts={}; _creds_store={"sid":None,"secret":None}; _users={}; _courses={}; _classes={}
    _webhooks=[]; _feedbacks=[]; _sessions={}; _profiles={}

    def init_db(): pass
    def get_creds(): return _creds_store["sid"],_creds_store["secret"]
    def set_creds(sid,secret): _creds_store["sid"]=sid; _creds_store["secret"]=secret

    def get_account(u): return _accounts.get(u)
    def set_account(u,ph,role,dn,uid="",tz="Asia/Seoul"):
        _accounts[u]={"username":u,"password_hash":ph,"role":role,"displayName":dn,"classInUid":uid,"timezone":tz,"created":datetime.now().isoformat()}
    def update_password(u,ph):
        if u in _accounts: _accounts[u]["password_hash"]=ph
    def del_account(u): _accounts.pop(u,None); delete_user_sessions(u)
    def list_accounts(): return [{k:v for k,v in a.items() if k!="password_hash"} for a in _accounts.values()]
    def has_admin(): return any(a["role"]=="admin" for a in _accounts.values())

    def create_session(token,username,role,uid,dn,tz="Asia/Seoul"):
        _sessions[token]={"username":username,"role":role,"classInUid":uid,"displayName":dn,"timezone":tz,
                          "expires":datetime.utcnow()+timedelta(days=SESSION_EXPIRY_DAYS)}
    def get_session(token):
        s=_sessions.get(token)
        if s and s["expires"]>datetime.utcnow(): return {k:v for k,v in s.items() if k!="expires"}
        if s: del _sessions[token]
        return None
    def delete_session(token): _sessions.pop(token,None)
    def delete_user_sessions(u):
        for t in [t for t,s in _sessions.items() if s["username"]==u]: del _sessions[t]

    def set_user(uid,tel,nick,role): _users[uid]={"uid":uid,"telephone":tel,"nickname":nick,"role":role,"status":"active"}
    def list_users(role=None,search="",page=1,per_page=50):
        u=list(_users.values())
        if role: u=[x for x in u if x["role"]==role]
        if search: s=search.lower(); u=[x for x in u if s in x.get("nickname","").lower() or s in x.get("telephone","").lower()]
        total=len(u); start=(page-1)*per_page; return u[start:start+per_page], total

    def get_student_profile(uid): return _profiles.get(uid,{"uid":uid,"topik_level":"","purpose":"","notes":"","native_lang":""})
    def set_student_profile(uid,topik="",purpose="",notes="",native_lang=""): _profiles[uid]={"uid":uid,"topik_level":topik,"purpose":purpose,"notes":notes,"native_lang":native_lang}

    def set_course(cid,name,tuid=""): _courses[cid]={"courseId":cid,"name":name,"teacherUid":tuid}
    def list_courses(tuid=None):
        c=list(_courses.values()); return [x for x in c if x["teacherUid"]==tuid] if tuid else c

    def set_class(clid,coid,name,begin,end,tuid): _classes[clid]={"classId":clid,"courseId":coid,"name":name,"begin":begin,"end":end,"teacherUid":tuid}
    def del_class(clid): _classes.pop(clid,None)
    def list_classes(course_id=None,teacher_uid=None):
        c=list(_classes.values())
        if course_id: c=[x for x in c if x["courseId"]==course_id]
        if teacher_uid: c=[x for x in c if x["teacherUid"]==teacher_uid]
        return sorted(c, key=lambda x: x.get("begin",0))

    def add_webhook(cmd,sid,data):
        _webhooks.append({"timestamp":datetime.now().isoformat(),"cmd":cmd,"sid":sid,"data":data})
        if len(_webhooks)>500: _webhooks[:]=_webhooks[-500:]
    def list_webhooks(limit=50): return _webhooks[-limit:],len(_webhooks)
    def get_webhook_stats():
        from collections import Counter; c=Counter(w["cmd"] for w in _webhooks)
        return [{"cmd":k,"cnt":v} for k,v in c.most_common()]

    def add_feedback(coid,clid,tuid,suid,comment):
        _feedbacks.append({"courseId":coid,"classId":clid,"teacherUid":tuid,"studentUid":suid,"comment":comment,"date":datetime.now().isoformat()})
    def list_feedbacks(tuid=None):
        f=_feedbacks; return [x for x in f if x["teacherUid"]==tuid] if tuid else f

    def count_all():
        return {"teachers":len([u for u in _users.values() if u["role"]=="teacher"]),
                "students":len([u for u in _users.values() if u["role"]=="student"]),
                "courses":len(_courses),"classes":len(_classes),"webhooks":len(_webhooks),"feedbacks":len(_feedbacks)}
    print("[DB] In-memory mode")
