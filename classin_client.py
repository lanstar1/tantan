"""
ClassIn API Client - Complete v1/v2 dual support
v1: POST /partner/api/course.api.php?action=XXX  (form-data + safeKey)
v2: POST /api/v2/XXX  (JSON + X-EEO-SIGN header)
"""
import hashlib
import time
import httpx

API_BASE = "https://api.eeo.cn"

def _ts():
    return int(time.time())

# ─── v1 Auth ──────────────────────────────────────────────────────
def _v1_safe_key(secret, ts):
    return hashlib.md5(f"{secret}{ts}".encode()).hexdigest()

async def call_v1(action, sid, secret, params=None):
    ts = _ts()
    data = {"SID": sid, "timeStamp": str(ts), "safeKey": _v1_safe_key(secret, ts)}
    if params:
        data.update(params)
    url = f"{API_BASE}/partner/api/course.api.php?action={action}"
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(url, data=data)
        try:
            return r.json()
        except:
            return {"error_info": {"errno": -1, "error": f"Non-JSON response (HTTP {r.status_code})"}}

# ─── v2 Auth ──────────────────────────────────────────────────────
def _v2_sign(sid, secret, ts, body=None):
    p = {}
    if body:
        for k, v in body.items():
            if not isinstance(v, (list, dict)) and len(str(v).encode()) <= 1024:
                p[k] = str(v)
    p["sid"], p["timeStamp"] = str(sid), str(ts)
    s = "&".join(f"{k}={p[k]}" for k in sorted(p))
    return hashlib.md5(f"{s}&key={secret}".encode()).hexdigest()

async def call_v2(endpoint, sid, secret, body=None):
    ts = _ts()
    headers = {
        "X-EEO-SIGN": _v2_sign(sid, secret, ts, body),
        "X-EEO-UID": str(sid), "X-EEO-TS": str(ts),
        "Content-Type": "application/json",
    }
    url = f"{API_BASE}/api/v2/{endpoint}"
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(url, json=body or {}, headers=headers)
        try:
            return r.json()
        except:
            return {"code": -1, "msg": f"Non-JSON response (HTTP {r.status_code})"}

# ─── Helper: parse v1 response ────────────────────────────────────
def parse_v1(result):
    ei = result.get("error_info", {})
    errno = ei.get("errno", 0)
    error = ei.get("error", "")
    data = result.get("data")
    return errno, error, data

# ─── Stage 1: Connection Test ─────────────────────────────────────
async def test_connection(sid, secret):
    try:
        result = await call_v1("register", sid, secret, {
            "telephone": "000-00000000",
            "password": hashlib.md5(b"test_conn").hexdigest(),
        })
        errno, error, _ = parse_v1(result)
        if errno in [102, 301, 302, 303, 304]:
            return {"success": False, "message": f"인증 실패 (errno={errno}): {error}", "raw": result}
        return {"success": True, "message": f"✅ API 인증 성공! (errno={errno})", "raw": result}
    except Exception as e:
        return {"success": False, "message": f"오류: {e}", "raw": None}

# ─── Stage 2: User Management ─────────────────────────────────────
async def register_user(sid, secret, telephone, password, nickname="", add_to_school=0):
    params = {"telephone": telephone, "password": hashlib.md5(password.encode()).hexdigest()}
    if nickname: params["nickname"] = nickname
    if add_to_school: params["addToSchoolMember"] = str(add_to_school)
    return await call_v1("register", sid, secret, params)

async def add_teacher(sid, secret, account, name):
    return await call_v1("addTeacher", sid, secret, {"teacherAccount": account, "teacherName": name})

async def add_student(sid, secret, account, name):
    return await call_v1("addSchoolStudent", sid, secret, {"studentAccount": account, "studentName": name})

async def edit_teacher(sid, secret, uid, name):
    return await call_v1("editTeacher", sid, secret, {"teacherUid": str(uid), "teacherName": name})

async def edit_student(sid, secret, uid, name):
    return await call_v1("editSchoolStudent", sid, secret, {"studentUid": str(uid), "studentName": name})

# ─── Stage 3: Course & Class ──────────────────────────────────────
async def create_course(sid, secret, name, teacher_uid=None, folder_id=None):
    p = {"courseName": name}
    if teacher_uid: p["mainTeacherUid"] = str(teacher_uid)
    if folder_id: p["folderId"] = str(folder_id)
    return await call_v1("addCourse", sid, secret, p)

async def edit_course(sid, secret, course_id, name=None, teacher_uid=None):
    p = {"courseId": str(course_id)}
    if name: p["courseName"] = name
    if teacher_uid: p["mainTeacherUid"] = str(teacher_uid)
    return await call_v1("editCourse", sid, secret, p)

async def create_class(sid, secret, course_id, class_name, begin_time, end_time, teacher_uid, seat_num=0):
    p = {
        "courseId": str(course_id), "className": class_name,
        "beginTime": str(begin_time), "endTime": str(end_time),
        "teacherUid": str(teacher_uid),
    }
    if seat_num: p["seatNum"] = str(seat_num)
    return await call_v1("addCourseClass", sid, secret, p)

async def edit_class(sid, secret, course_id, class_id, **kwargs):
    p = {"courseId": str(course_id), "classId": str(class_id)}
    p.update({k: str(v) for k, v in kwargs.items()})
    return await call_v1("editCourseClass", sid, secret, p)

async def delete_class(sid, secret, course_id, class_id):
    return await call_v1("delCourseClass", sid, secret, {
        "courseId": str(course_id), "classId": str(class_id)
    })

async def add_course_student(sid, secret, course_id, student_uid):
    return await call_v1("addCourseStudent", sid, secret, {
        "courseId": str(course_id), "studentUid": str(student_uid)
    })

async def del_course_student(sid, secret, course_id, student_uid):
    return await call_v1("delCourseStudent", sid, secret, {
        "courseId": str(course_id), "studentUid": str(student_uid)
    })

async def add_course_teacher(sid, secret, course_id, teacher_uid):
    return await call_v1("addCourseTeacher", sid, secret, {
        "courseId": str(course_id), "teacherUid": str(teacher_uid)
    })

# ─── Stage 4: Login Link ──────────────────────────────────────────
async def get_login_link(sid, secret, uid):
    return await call_v1("getLoginLinked", sid, secret, {"uid": str(uid)})

# ─── Stage 5: Webhook verification ────────────────────────────────
def verify_webhook_safe_key(secret, timestamp, safe_key):
    expected = hashlib.md5(f"{secret}{timestamp}".encode()).hexdigest()
    return expected == safe_key

# ─── Stage 6: Feedback ────────────────────────────────────────────
async def update_class_student_comment(sid, secret, course_id, class_id, teacher_uid, student_uid, comment):
    return await call_v1("updateClassStudentComment", sid, secret, {
        "courseId": str(course_id), "classId": str(class_id),
        "teacherUid": str(teacher_uid), "studentUid": str(student_uid),
        "comment": comment,
    })
