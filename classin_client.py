"""ClassIn API Client v3 - Complete with Cloud Drive"""
import hashlib, time, httpx

API_BASE = "https://api.eeo.cn"
def _ts(): return int(time.time())
def _v1_safe_key(secret, ts): return hashlib.md5(f"{secret}{ts}".encode()).hexdigest()

async def call_v1(action, sid, secret, params=None):
    ts = _ts()
    data = {"SID": sid, "timeStamp": str(ts), "safeKey": _v1_safe_key(secret, ts)}
    if params: data.update(params)
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{API_BASE}/partner/api/course.api.php?action={action}", data=data)
        try: return r.json()
        except: return {"error_info": {"errno": -1, "error": f"HTTP {r.status_code}"}}

def _v2_sign(sid, secret, ts, body=None):
    p = {}
    if body:
        for k, v in body.items():
            if not isinstance(v, (list, dict)) and len(str(v).encode()) <= 1024: p[k] = str(v)
    p["sid"], p["timeStamp"] = str(sid), str(ts)
    s = "&".join(f"{k}={p[k]}" for k in sorted(p))
    return hashlib.md5(f"{s}&key={secret}".encode()).hexdigest()

async def call_v2(endpoint, sid, secret, body=None):
    ts = _ts()
    headers = {"X-EEO-SIGN": _v2_sign(sid, secret, ts, body), "X-EEO-UID": str(sid),
               "X-EEO-TS": str(ts), "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{API_BASE}/api/v2/{endpoint}", json=body or {}, headers=headers)
        try: return r.json()
        except: return {"code": -1, "msg": f"HTTP {r.status_code}"}

def parse_v1(result):
    ei = result.get("error_info", {})
    return ei.get("errno", 0), ei.get("error", ""), result.get("data")

# Connection
async def test_connection(sid, secret):
    try:
        result = await call_v1("register", sid, secret, {"telephone":"000-00000000","password":hashlib.md5(b"test").hexdigest()})
        e, err, _ = parse_v1(result)
        if e in [102, 301, 302, 303]: return {"success": False, "message": f"인증 실패 ({e}): {err}", "raw": result}
        return {"success": True, "message": f"✅ API 인증 성공! ({e})", "raw": result}
    except Exception as ex: return {"success": False, "message": str(ex), "raw": None}

# Users
async def register_user(sid, secret, tel, pw, nick="", add=0):
    p = {"telephone": tel, "password": hashlib.md5(pw.encode()).hexdigest()}
    if nick: p["nickname"] = nick
    if add: p["addToSchoolMember"] = str(add)
    return await call_v1("register", sid, secret, p)
async def add_teacher(sid, secret, acc, name): return await call_v1("addTeacher", sid, secret, {"teacherAccount": acc, "teacherName": name})
async def add_student(sid, secret, acc, name): return await call_v1("addSchoolStudent", sid, secret, {"studentAccount": acc, "studentName": name})
async def edit_teacher(sid, secret, uid, name): return await call_v1("editTeacher", sid, secret, {"teacherUid": str(uid), "teacherName": name})
async def edit_student(sid, secret, uid, name): return await call_v1("editSchoolStudent", sid, secret, {"studentUid": str(uid), "studentName": name})

# Courses & Classes
async def create_course(sid, secret, name, tuid=None):
    p = {"courseName": name}
    if tuid: p["mainTeacherUid"] = str(tuid)
    return await call_v1("addCourse", sid, secret, p)
async def create_class(sid, secret, cid, name, begin, end, tuid, seat=0):
    p = {"courseId": str(cid), "className": name, "beginTime": str(begin), "endTime": str(end), "teacherUid": str(tuid)}
    if seat: p["seatNum"] = str(seat)
    return await call_v1("addCourseClass", sid, secret, p)
async def delete_class(sid, secret, cid, clid): return await call_v1("delCourseClass", sid, secret, {"courseId": str(cid), "classId": str(clid)})
async def add_course_student(sid, secret, cid, suid): return await call_v1("addCourseStudent", sid, secret, {"courseId": str(cid), "studentUid": str(suid)})
async def add_course_teacher(sid, secret, cid, tuid): return await call_v1("addCourseTeacher", sid, secret, {"courseId": str(cid), "teacherUid": str(tuid)})
async def get_login_link(sid, secret, uid): return await call_v1("getLoginLinked", sid, secret, {"uid": str(uid)})
async def update_class_student_comment(sid, secret, cid, clid, tuid, suid, comment):
    return await call_v1("updateClassStudentComment", sid, secret, {"courseId": str(cid), "classId": str(clid), "teacherUid": str(tuid), "studentUid": str(suid), "comment": comment})

# Cloud Drive
async def get_top_folder(sid, secret): return await call_v1("getTopFolderId", sid, secret)
async def get_folder_list(sid, secret, folder_id): return await call_v1("getFolderList", sid, secret, {"folderId": str(folder_id)})
async def get_cloud_list(sid, secret, folder_id): return await call_v1("getCloudList", sid, secret, {"folderId": str(folder_id)})

# Webhook
def verify_webhook_safe_key(secret, ts, sk): return hashlib.md5(f"{secret}{ts}".encode()).hexdigest() == sk
