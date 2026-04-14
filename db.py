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
            cur.execute("""CREATE TABLE IF NOT EXISTS availability (
                id SERIAL PRIMARY KEY, teacher_uid TEXT NOT NULL, teacher_name TEXT DEFAULT '',
                slot_date DATE NOT NULL, start_time TEXT NOT NULL, end_time TEXT NOT NULL,
                status TEXT DEFAULT 'available', created_at TIMESTAMPTZ DEFAULT NOW())""")
            cur.execute("""CREATE TABLE IF NOT EXISTS teacher_profiles (
                uid TEXT PRIMARY KEY, bio TEXT DEFAULT '', career TEXT DEFAULT '',
                intro_video TEXT DEFAULT '', photo_url TEXT DEFAULT '', certificates TEXT DEFAULT '',
                hourly_rate INTEGER DEFAULT 0)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS announcements (
                id SERIAL PRIMARY KEY, title TEXT, content TEXT, author TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW())""")
            cur.execute("""CREATE TABLE IF NOT EXISTS inquiries (
                id SERIAL PRIMARY KEY, from_user TEXT, subject TEXT, content TEXT,
                reply TEXT DEFAULT '', status TEXT DEFAULT 'open', created_at TIMESTAMPTZ DEFAULT NOW())""")
            cur.execute("""CREATE TABLE IF NOT EXISTS absences (
                id SERIAL PRIMARY KEY, teacher_uid TEXT, class_id TEXT,
                reason TEXT DEFAULT '', photo_url TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT NOW())""")
            cur.execute("""CREATE TABLE IF NOT EXISTS ratings (
                id SERIAL PRIMARY KEY, class_id TEXT, course_id TEXT,
                student_uid TEXT, teacher_uid TEXT, score INTEGER DEFAULT 5,
                review TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT NOW())""")
            cur.execute("""CREATE TABLE IF NOT EXISTS curriculum (
                id SERIAL PRIMARY KEY, course_level TEXT NOT NULL, unit_number INTEGER NOT NULL,
                unit_title TEXT NOT NULL, description TEXT DEFAULT '', key_points TEXT DEFAULT '[]',
                materials_ref TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW())""")
            cur.execute("""CREATE TABLE IF NOT EXISTS student_progress (
                id SERIAL PRIMARY KEY, student_uid TEXT NOT NULL, course_id TEXT DEFAULT '',
                curriculum_id INTEGER, status TEXT DEFAULT 'pending',
                teacher_uid TEXT DEFAULT '', notes TEXT DEFAULT '',
                completed_at TIMESTAMPTZ, updated_at TIMESTAMPTZ DEFAULT NOW())""")
            cur.execute("""CREATE TABLE IF NOT EXISTS teaching_guides (
                id SERIAL PRIMARY KEY, curriculum_id INTEGER, guide_type TEXT DEFAULT 'admin',
                content TEXT NOT NULL, target_lang TEXT DEFAULT '',
                created_by TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT NOW())""")
            cur.execute("""CREATE TABLE IF NOT EXISTS class_recordings (
                id SERIAL PRIMARY KEY, class_id TEXT, course_id TEXT,
                class_name TEXT DEFAULT '', replay_url TEXT DEFAULT '', live_url TEXT DEFAULT '',
                teacher_uid TEXT DEFAULT '', is_featured BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW())""")
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
    def del_user(uid):
        with _conn() as c:
            cur=c.cursor(); cur.execute("DELETE FROM classin_users WHERE uid=%s",(uid,))
            cur.execute("DELETE FROM student_profiles WHERE uid=%s",(uid,)); c.commit()
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
    def del_course(cid):
        with _conn() as c:
            cur=c.cursor(); cur.execute("DELETE FROM courses WHERE course_id=%s",(cid,))
            cur.execute("DELETE FROM classes WHERE course_id=%s",(cid,)); c.commit()
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

    # Availability
    def add_availability(teacher_uid, teacher_name, slot_date, start_time, end_time):
        with _conn() as c:
            cur=c.cursor(); cur.execute("INSERT INTO availability(teacher_uid,teacher_name,slot_date,start_time,end_time)VALUES(%s,%s,%s,%s,%s) RETURNING id",
                (teacher_uid,teacher_name,slot_date,start_time,end_time)); aid=cur.fetchone()["id"]; c.commit(); return aid
    def list_availability(teacher_uid=None):
        with _conn() as c:
            cur=c.cursor()
            if teacher_uid: cur.execute("SELECT * FROM availability WHERE teacher_uid=%s ORDER BY slot_date,start_time",(teacher_uid,))
            else: cur.execute("SELECT * FROM availability ORDER BY slot_date,start_time")
            return [{"id":r["id"],"teacherUid":r["teacher_uid"],"teacherName":r["teacher_name"],
                     "date":str(r["slot_date"]),"startTime":r["start_time"],"endTime":r["end_time"],
                     "status":r["status"]} for r in cur.fetchall()]
    def del_availability(aid):
        with _conn() as c:
            c.cursor().execute("DELETE FROM availability WHERE id=%s",(aid,)); c.commit()
    def update_availability_status(aid, status):
        with _conn() as c:
            c.cursor().execute("UPDATE availability SET status=%s WHERE id=%s",(status,aid)); c.commit()

    # Teacher Profiles
    def get_teacher_profile(uid):
        with _conn() as c:
            cur=c.cursor(); cur.execute("SELECT * FROM teacher_profiles WHERE uid=%s",(uid,))
            r=cur.fetchone()
            return dict(r) if r else {"uid":uid,"bio":"","career":"","intro_video":"","photo_url":"","certificates":"","hourly_rate":0}
    def set_teacher_profile(uid, bio="", career="", intro_video="", photo_url="", certificates="", hourly_rate=0):
        with _conn() as c:
            c.cursor().execute("""INSERT INTO teacher_profiles(uid,bio,career,intro_video,photo_url,certificates,hourly_rate)
                VALUES(%s,%s,%s,%s,%s,%s,%s)ON CONFLICT(uid)DO UPDATE SET bio=%s,career=%s,intro_video=%s,photo_url=%s,certificates=%s,hourly_rate=%s""",
                (uid,bio,career,intro_video,photo_url,certificates,hourly_rate,bio,career,intro_video,photo_url,certificates,hourly_rate)); c.commit()

    # Announcements
    def add_announcement(title, content, author):
        with _conn() as c:
            c.cursor().execute("INSERT INTO announcements(title,content,author)VALUES(%s,%s,%s)",(title,content,author)); c.commit()
    def list_announcements():
        with _conn() as c:
            cur=c.cursor(); cur.execute("SELECT * FROM announcements ORDER BY created_at DESC")
            return [{"id":r["id"],"title":r["title"],"content":r["content"],"author":r["author"],"date":str(r["created_at"])} for r in cur.fetchall()]
    def del_announcement(aid):
        with _conn() as c:
            c.cursor().execute("DELETE FROM announcements WHERE id=%s",(aid,)); c.commit()

    # Inquiries
    def add_inquiry(from_user, subject, content):
        with _conn() as c:
            c.cursor().execute("INSERT INTO inquiries(from_user,subject,content)VALUES(%s,%s,%s)",(from_user,subject,content)); c.commit()
    def list_inquiries(from_user=None):
        with _conn() as c:
            cur=c.cursor()
            if from_user: cur.execute("SELECT * FROM inquiries WHERE from_user=%s ORDER BY created_at DESC",(from_user,))
            else: cur.execute("SELECT * FROM inquiries ORDER BY created_at DESC")
            return [{"id":r["id"],"from":r["from_user"],"subject":r["subject"],"content":r["content"],
                     "reply":r["reply"],"status":r["status"],"date":str(r["created_at"])} for r in cur.fetchall()]
    def reply_inquiry(iid, reply):
        with _conn() as c:
            c.cursor().execute("UPDATE inquiries SET reply=%s,status='replied' WHERE id=%s",(reply,iid)); c.commit()

    # Absences
    def add_absence(teacher_uid, class_id, reason, photo_url=""):
        with _conn() as c:
            c.cursor().execute("INSERT INTO absences(teacher_uid,class_id,reason,photo_url)VALUES(%s,%s,%s,%s)",
                (teacher_uid,class_id,reason,photo_url)); c.commit()
    def list_absences(teacher_uid=None):
        with _conn() as c:
            cur=c.cursor()
            if teacher_uid: cur.execute("SELECT * FROM absences WHERE teacher_uid=%s ORDER BY created_at DESC",(teacher_uid,))
            else: cur.execute("SELECT * FROM absences ORDER BY created_at DESC")
            return [{"id":r["id"],"teacherUid":r["teacher_uid"],"classId":r["class_id"],
                     "reason":r["reason"],"photoUrl":r["photo_url"],"date":str(r["created_at"])} for r in cur.fetchall()]

    # Ratings
    def add_rating(class_id, course_id, student_uid, teacher_uid, score, review=""):
        with _conn() as c:
            c.cursor().execute("INSERT INTO ratings(class_id,course_id,student_uid,teacher_uid,score,review)VALUES(%s,%s,%s,%s,%s,%s)",
                (class_id,course_id,student_uid,teacher_uid,score,review)); c.commit()
    def list_ratings(teacher_uid=None):
        with _conn() as c:
            cur=c.cursor()
            if teacher_uid: cur.execute("SELECT * FROM ratings WHERE teacher_uid=%s ORDER BY created_at DESC",(teacher_uid,))
            else: cur.execute("SELECT * FROM ratings ORDER BY created_at DESC")
            return [{"id":r["id"],"classId":r["class_id"],"courseId":r["course_id"],"studentUid":r["student_uid"],
                     "teacherUid":r["teacher_uid"],"score":r["score"],"review":r["review"],"date":str(r["created_at"])} for r in cur.fetchall()]
    def get_teacher_stats(teacher_uid=None):
        with _conn() as c:
            cur=c.cursor()
            q="SELECT teacher_uid, COUNT(*) as cnt, COALESCE(AVG(score),0) as avg_score FROM ratings"
            if teacher_uid: q+=" WHERE teacher_uid=%s"; cur.execute(q+" GROUP BY teacher_uid",(teacher_uid,))
            else: cur.execute(q+" GROUP BY teacher_uid")
            return [{"teacherUid":r["teacher_uid"],"ratingCount":r["cnt"],"avgScore":round(float(r["avg_score"]),1)} for r in cur.fetchall()]

    # Curriculum
    def add_curriculum(level, unit_num, title, desc="", key_points="[]", materials=""):
        with _conn() as c:
            cur=c.cursor(); cur.execute("INSERT INTO curriculum(course_level,unit_number,unit_title,description,key_points,materials_ref)VALUES(%s,%s,%s,%s,%s,%s)RETURNING id",
                (level,unit_num,title,desc,key_points,materials)); cid=cur.fetchone()["id"]; c.commit(); return cid
    def update_curriculum(cid, level, unit_num, title, desc="", key_points="[]", materials=""):
        with _conn() as c:
            c.cursor().execute("UPDATE curriculum SET course_level=%s,unit_number=%s,unit_title=%s,description=%s,key_points=%s,materials_ref=%s,updated_at=NOW() WHERE id=%s",
                (level,unit_num,title,desc,key_points,materials,cid)); c.commit()
    def del_curriculum(cid):
        with _conn() as c:
            cur=c.cursor(); cur.execute("DELETE FROM curriculum WHERE id=%s",(cid,))
            cur.execute("DELETE FROM student_progress WHERE curriculum_id=%s",(cid,))
            cur.execute("DELETE FROM teaching_guides WHERE curriculum_id=%s",(cid,)); c.commit()
    def list_curriculum(level=None):
        with _conn() as c:
            cur=c.cursor()
            if level: cur.execute("SELECT * FROM curriculum WHERE course_level=%s ORDER BY unit_number",(level,))
            else: cur.execute("SELECT * FROM curriculum ORDER BY course_level, unit_number")
            return [{"id":r["id"],"level":r["course_level"],"unitNumber":r["unit_number"],"title":r["unit_title"],
                     "description":r["description"],"keyPoints":r["key_points"],"materials":r["materials_ref"],
                     "updated":str(r["updated_at"])} for r in cur.fetchall()]
    def get_curriculum(cid):
        with _conn() as c:
            cur=c.cursor(); cur.execute("SELECT * FROM curriculum WHERE id=%s",(cid,))
            r=cur.fetchone()
            if r: return {"id":r["id"],"level":r["course_level"],"unitNumber":r["unit_number"],"title":r["unit_title"],
                          "description":r["description"],"keyPoints":r["key_points"],"materials":r["materials_ref"]}
            return None

    # Student Progress
    def set_progress(student_uid, curriculum_id, status, teacher_uid="", notes="", course_id=""):
        with _conn() as c:
            cur=c.cursor(); cur.execute("""INSERT INTO student_progress(student_uid,curriculum_id,status,teacher_uid,notes,course_id,updated_at,completed_at)
                VALUES(%s,%s,%s,%s,%s,%s,NOW(),CASE WHEN %s='completed' THEN NOW() ELSE NULL END)
                ON CONFLICT DO NOTHING""",
                (student_uid,curriculum_id,status,teacher_uid,notes,course_id,status))
            cur.execute("UPDATE student_progress SET status=%s,notes=%s,updated_at=NOW(),completed_at=CASE WHEN %s='completed' THEN NOW() ELSE completed_at END WHERE student_uid=%s AND curriculum_id=%s",
                (status,notes,status,student_uid,curriculum_id)); c.commit()
    def get_progress(student_uid, course_id=None):
        with _conn() as c:
            cur=c.cursor()
            q="""SELECT sp.*, c.course_level, c.unit_number, c.unit_title FROM student_progress sp
                 LEFT JOIN curriculum c ON sp.curriculum_id=c.id WHERE sp.student_uid=%s"""
            p=[student_uid]
            if course_id: q+=" AND sp.course_id=%s"; p.append(course_id)
            cur.execute(q+" ORDER BY c.course_level, c.unit_number", p)
            return [{"id":r["id"],"studentUid":r["student_uid"],"curriculumId":r["curriculum_id"],
                     "status":r["status"],"notes":r["notes"],"teacherUid":r["teacher_uid"],
                     "level":r.get("course_level",""),"unitNumber":r.get("unit_number",0),
                     "unitTitle":r.get("unit_title",""),"updated":str(r["updated_at"]),
                     "completed":str(r["completed_at"]) if r["completed_at"] else None} for r in cur.fetchall()]
    def get_teacher_students_progress(teacher_uid):
        with _conn() as c:
            cur=c.cursor()
            cur.execute("""SELECT sp.student_uid, cu.nickname, c.course_level, c.unit_number, c.unit_title, sp.status, sp.notes
                FROM student_progress sp
                LEFT JOIN curriculum c ON sp.curriculum_id=c.id
                LEFT JOIN classin_users cu ON sp.student_uid=cu.uid
                WHERE sp.teacher_uid=%s ORDER BY cu.nickname, c.course_level, c.unit_number""", (teacher_uid,))
            return [{"studentUid":r["student_uid"],"studentName":r.get("nickname",""),"level":r.get("course_level",""),
                     "unitNumber":r.get("unit_number",0),"unitTitle":r.get("unit_title",""),
                     "status":r["status"],"notes":r["notes"]} for r in cur.fetchall()]

    # Teaching Guides
    def add_guide(curriculum_id, content, guide_type="admin", target_lang="", created_by=""):
        with _conn() as c:
            cur=c.cursor(); cur.execute("INSERT INTO teaching_guides(curriculum_id,content,guide_type,target_lang,created_by)VALUES(%s,%s,%s,%s,%s)RETURNING id",
                (curriculum_id,content,guide_type,target_lang,created_by)); gid=cur.fetchone()["id"]; c.commit(); return gid
    def list_guides(curriculum_id=None):
        with _conn() as c:
            cur=c.cursor()
            if curriculum_id: cur.execute("SELECT * FROM teaching_guides WHERE curriculum_id=%s ORDER BY created_at DESC",(curriculum_id,))
            else: cur.execute("SELECT * FROM teaching_guides ORDER BY curriculum_id, created_at DESC")
            return [{"id":r["id"],"curriculumId":r["curriculum_id"],"content":r["content"],
                     "guideType":r["guide_type"],"targetLang":r["target_lang"],
                     "createdBy":r["created_by"],"date":str(r["created_at"])} for r in cur.fetchall()]
    def del_guide(gid):
        with _conn() as c:
            c.cursor().execute("DELETE FROM teaching_guides WHERE id=%s",(gid,)); c.commit()

    # Class Recordings
    def add_recording(class_id, course_id, class_name, replay_url="", live_url="", teacher_uid="", featured=False):
        with _conn() as c:
            c.cursor().execute("""INSERT INTO class_recordings(class_id,course_id,class_name,replay_url,live_url,teacher_uid,is_featured)
                VALUES(%s,%s,%s,%s,%s,%s,%s)ON CONFLICT DO NOTHING""",
                (class_id,course_id,class_name,replay_url,live_url,teacher_uid,featured)); c.commit()
    def list_recordings(teacher_uid=None, featured_only=False):
        with _conn() as c:
            cur=c.cursor(); q="SELECT * FROM class_recordings WHERE 1=1"; p=[]
            if teacher_uid: q+=" AND teacher_uid=%s"; p.append(teacher_uid)
            if featured_only: q+=" AND is_featured=TRUE"
            cur.execute(q+" ORDER BY created_at DESC", p)
            return [{"id":r["id"],"classId":r["class_id"],"courseId":r["course_id"],"className":r["class_name"],
                     "replayUrl":r["replay_url"],"liveUrl":r["live_url"],"teacherUid":r["teacher_uid"],
                     "featured":r["is_featured"],"date":str(r["created_at"])} for r in cur.fetchall()]
    def toggle_featured(rec_id, featured):
        with _conn() as c:
            c.cursor().execute("UPDATE class_recordings SET is_featured=%s WHERE id=%s",(featured,rec_id)); c.commit()

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
    _webhooks=[]; _feedbacks=[]; _sessions={}; _profiles={}; _avail=[]; _avail_counter=[0]
    _teacher_profiles={}; _announcements=[]; _ann_counter=[0]; _inquiries=[]; _inq_counter=[0]
    _absences=[]; _abs_counter=[0]; _ratings=[]; _rat_counter=[0]

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
    def del_user(uid):
        with _conn() as c:
            cur=c.cursor(); cur.execute("DELETE FROM classin_users WHERE uid=%s",(uid,))
            cur.execute("DELETE FROM student_profiles WHERE uid=%s",(uid,)); c.commit()
    def list_users(role=None,search="",page=1,per_page=50):
        u=list(_users.values())
        if role: u=[x for x in u if x["role"]==role]
        if search: s=search.lower(); u=[x for x in u if s in x.get("nickname","").lower() or s in x.get("telephone","").lower()]
        total=len(u); start=(page-1)*per_page; return u[start:start+per_page], total

    def get_student_profile(uid): return _profiles.get(uid,{"uid":uid,"topik_level":"","purpose":"","notes":"","native_lang":""})
    def set_student_profile(uid,topik="",purpose="",notes="",native_lang=""): _profiles[uid]={"uid":uid,"topik_level":topik,"purpose":purpose,"notes":notes,"native_lang":native_lang}

    def del_user(uid): _users.pop(uid,None); _profiles.pop(uid,None)
    def del_course(cid):
        _courses.pop(cid,None)
        to_del=[k for k,v in _classes.items() if v.get("courseId")==cid]
        for k in to_del: _classes.pop(k,None)

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

    def add_availability(teacher_uid, teacher_name, slot_date, start_time, end_time):
        _avail_counter[0]+=1; aid=_avail_counter[0]
        _avail.append({"id":aid,"teacherUid":teacher_uid,"teacherName":teacher_name,
                       "date":slot_date,"startTime":start_time,"endTime":end_time,"status":"available"})
        return aid
    def list_availability(teacher_uid=None):
        a=_avail; return [x for x in a if x["teacherUid"]==teacher_uid] if teacher_uid else a
    def del_availability(aid):
        _avail[:]=[x for x in _avail if x["id"]!=aid]
    def update_availability_status(aid, status):
        for a in _avail:
            if a["id"]==aid: a["status"]=status

    # Teacher Profiles
    def get_teacher_profile(uid): return _teacher_profiles.get(uid,{"uid":uid,"bio":"","career":"","intro_video":"","photo_url":"","certificates":"","hourly_rate":0})
    def set_teacher_profile(uid,bio="",career="",intro_video="",photo_url="",certificates="",hourly_rate=0):
        _teacher_profiles[uid]={"uid":uid,"bio":bio,"career":career,"intro_video":intro_video,"photo_url":photo_url,"certificates":certificates,"hourly_rate":hourly_rate}

    # Announcements
    def add_announcement(title,content,author):
        _ann_counter[0]+=1; _announcements.insert(0,{"id":_ann_counter[0],"title":title,"content":content,"author":author,"date":datetime.now().isoformat()})
    def list_announcements(): return _announcements
    def del_announcement(aid): _announcements[:]=[a for a in _announcements if a["id"]!=aid]

    # Inquiries
    def add_inquiry(from_user,subject,content):
        _inq_counter[0]+=1; _inquiries.insert(0,{"id":_inq_counter[0],"from":from_user,"subject":subject,"content":content,"reply":"","status":"open","date":datetime.now().isoformat()})
    def list_inquiries(from_user=None):
        return [x for x in _inquiries if x["from"]==from_user] if from_user else _inquiries
    def reply_inquiry(iid,reply):
        for i in _inquiries:
            if i["id"]==iid: i["reply"]=reply; i["status"]="replied"

    # Absences
    def add_absence(teacher_uid,class_id,reason,photo_url=""):
        _abs_counter[0]+=1; _absences.insert(0,{"id":_abs_counter[0],"teacherUid":teacher_uid,"classId":class_id,"reason":reason,"photoUrl":photo_url,"date":datetime.now().isoformat()})
    def list_absences(teacher_uid=None):
        return [x for x in _absences if x["teacherUid"]==teacher_uid] if teacher_uid else _absences

    # Ratings
    def add_rating(class_id,course_id,student_uid,teacher_uid,score,review=""):
        _rat_counter[0]+=1; _ratings.insert(0,{"id":_rat_counter[0],"classId":class_id,"courseId":course_id,"studentUid":student_uid,"teacherUid":teacher_uid,"score":score,"review":review,"date":datetime.now().isoformat()})
    def list_ratings(teacher_uid=None):
        return [x for x in _ratings if x["teacherUid"]==teacher_uid] if teacher_uid else _ratings
    def get_teacher_stats(teacher_uid=None):
        r=_ratings
        if teacher_uid: r=[x for x in r if x["teacherUid"]==teacher_uid]
        if not r: return []
        from collections import defaultdict; d=defaultdict(list)
        for x in r: d[x["teacherUid"]].append(x["score"])
        return [{"teacherUid":k,"ratingCount":len(v),"avgScore":round(sum(v)/len(v),1)} for k,v in d.items()]

    def count_all():
        return {"teachers":len([u for u in _users.values() if u["role"]=="teacher"]),
                "students":len([u for u in _users.values() if u["role"]=="student"]),
                "courses":len(_courses),"classes":len(_classes),"webhooks":len(_webhooks),"feedbacks":len(_feedbacks)}

    # In-memory stubs for new tables
    _curriculum=[]; _cur_counter=[0]; _progress=[]; _prg_counter=[0]; _guides=[]; _gd_counter=[0]; _recordings=[]
    def add_curriculum(level,un,title,desc="",kp="[]",mat=""): _cur_counter[0]+=1; _curriculum.append({"id":_cur_counter[0],"level":level,"unitNumber":un,"title":title,"description":desc,"keyPoints":kp,"materials":mat,"updated":datetime.now().isoformat()}); return _cur_counter[0]
    def update_curriculum(cid,level,un,title,desc="",kp="[]",mat=""):
        for c in _curriculum:
            if c["id"]==cid: c.update({"level":level,"unitNumber":un,"title":title,"description":desc,"keyPoints":kp,"materials":mat})
    def del_curriculum(cid): _curriculum[:]=[c for c in _curriculum if c["id"]!=cid]
    def list_curriculum(level=None): return sorted([c for c in _curriculum if not level or c["level"]==level],key=lambda x:(x["level"],x["unitNumber"]))
    def get_curriculum(cid):
        for c in _curriculum:
            if c["id"]==cid: return c
        return None
    def set_progress(suid,cid,status,tuid="",notes="",course_id=""): _prg_counter[0]+=1; _progress.append({"id":_prg_counter[0],"studentUid":suid,"curriculumId":cid,"status":status,"teacherUid":tuid,"notes":notes,"level":"","unitNumber":0,"unitTitle":"","updated":datetime.now().isoformat(),"completed":None})
    def get_progress(suid,course_id=None): return [p for p in _progress if p["studentUid"]==suid]
    def get_teacher_students_progress(tuid): return [p for p in _progress if p["teacherUid"]==tuid]
    def add_guide(cid,content,gt="admin",tl="",cb=""): _gd_counter[0]+=1; _guides.append({"id":_gd_counter[0],"curriculumId":cid,"content":content,"guideType":gt,"targetLang":tl,"createdBy":cb,"date":datetime.now().isoformat()}); return _gd_counter[0]
    def list_guides(cid=None): return [g for g in _guides if not cid or g["curriculumId"]==cid]
    def del_guide(gid): _guides[:]=[g for g in _guides if g["id"]!=gid]
    def add_recording(clid,coid,cname,replay="",live="",tuid="",feat=False): _recordings.append({"id":len(_recordings)+1,"classId":clid,"courseId":coid,"className":cname,"replayUrl":replay,"liveUrl":live,"teacherUid":tuid,"featured":feat,"date":datetime.now().isoformat()})
    def list_recordings(tuid=None,featured_only=False): r=_recordings; (tuid and (r:=[x for x in r if x["teacherUid"]==tuid])); (featured_only and (r:=[x for x in r if x["featured"]])); return r
    def toggle_featured(rid,feat):
        for r in _recordings:
            if r["id"]==rid: r["featured"]=feat
    print("[DB] In-memory mode")
