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

def parse_v1_raw(result):
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
    p = {"telephone": tel, "password": pw}
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

# Cloud Drive (uses cloud.api.php, NOT course.api.php)
async def call_cloud_v1(action, sid, secret, params=None):
    ts = _ts()
    data = {"SID": sid, "timeStamp": str(ts), "safeKey": _v1_safe_key(secret, ts)}
    if params: data.update(params)
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{API_BASE}/partner/api/cloud.api.php?action={action}", data=data)
        try: return r.json()
        except: return {"error_info": {"errno": -1, "error": f"HTTP {r.status_code}"}}

async def upload_file_cloud(sid, secret, folder_id, file_bytes, filename):
    ts = _ts()
    data = {"SID": sid, "timeStamp": str(ts), "safeKey": _v1_safe_key(secret, ts), "folderId": str(folder_id)}
    files = {"Filedata": (filename, file_bytes)}
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{API_BASE}/partner/api/cloud.api.php?action=uploadFile", data=data, files=files)
        try: return r.json()
        except: return {"error_info": {"errno": -1, "error": f"HTTP {r.status_code}"}}

async def get_top_folder(sid, secret): return await call_cloud_v1("getTopFolderId", sid, secret)
async def get_folder_list(sid, secret, folder_id): return await call_cloud_v1("getFolderList", sid, secret, {"folderId": str(folder_id)})
async def get_cloud_list(sid, secret, folder_id): return await call_cloud_v1("getCloudList", sid, secret, {"folderId": str(folder_id)})
async def create_folder(sid, secret, parent_id, name): return await call_cloud_v1("createFolder", sid, secret, {"parentId": str(parent_id), "folderName": name})
async def rename_file(sid, secret, file_id, name): return await call_cloud_v1("renameFile", sid, secret, {"fileId": str(file_id), "fileName": name})
async def del_file(sid, secret, file_id): return await call_cloud_v1("delFile", sid, secret, {"fileId": str(file_id)})
async def rename_folder(sid, secret, folder_id, name): return await call_cloud_v1("renameFolder", sid, secret, {"folderId": str(folder_id), "folderName": name})
async def del_folder(sid, secret, folder_id): return await call_cloud_v1("delFolder", sid, secret, {"folderId": str(folder_id)})

# Broadcast - Recording & Live replay
async def get_webcast_url(sid, secret, course_id, class_id):
    return await call_v1("getWebcastUrl", sid, secret, {"courseId": str(course_id), "classId": str(class_id)})

# Labels
async def add_course_labels(sid, secret, course_id, labels):
    return await call_v1("addCourseLabels", sid, secret, {"courseId": str(course_id), "labels": labels})
async def add_class_labels(sid, secret, course_id, class_id, labels):
    return await call_v1("addClassLabels", sid, secret, {"courseId": str(course_id), "classId": str(class_id), "labels": labels})

# Webhook
def verify_webhook_safe_key(secret, ts, sk): return hashlib.md5(f"{secret}{ts}".encode()).hexdigest() == sk

# Chinese → Korean error translation
ERROR_KR = {
    "参数不全或错误": "파라미터 불완전 또는 오류",
    "无权限": "권한 없음 (SID/SECRET 확인)",
    "手机号码不合法": "전화번호 형식 오류 (00국가코드-번호)",
    "密码长度不合法（6-20位）": "비밀번호 6~20자 필요",
    "密码长度不合法": "비밀번호 6~20자 필요",
    "程序正常执行": "정상 처리",
    "该手机号已注册": "이미 등록된 전화번호",
    "该邮箱已注册": "이미 등록된 이메일",
    "用户不存在": "사용자 없음",
    "课程不存在": "코스 없음",
    "课程已结束": "코스 종료됨",
    "课节不存在": "수업 없음",
    "该学生已在课程中": "이미 배정된 학생",
    "该教师已在课程中": "이미 배정된 강사",
    "该用户不是机构的老师": "해당 사용자는 학교 강사가 아닙니다",
    "该用户不是机构的学生": "해당 사용자는 학교 학생이 아닙니다",
    "台上人数参数错误": "좌석 수 파라미터 오류",
    "safeKey错误": "인증키(safeKey) 오류",
    "时间戳过期": "타임스탬프 만료",
    "SID不存在": "SID 없음",
    "课程名不能为空": "코스 이름 필수",
    "上课时间不能早于当前时间": "수업 시작은 현재 시간 이후여야 합니다",
    "上课时间必须早于下课时间": "시작 시간이 종료 시간보다 앞이어야 합니다",
}

def translate_error(msg):
    if not msg: return msg
    for cn, kr in ERROR_KR.items():
        if cn in msg: return msg.replace(cn, kr)
    return msg

def parse_v1(result):
    e, err, data = parse_v1_raw(result)
    return e, translate_error(err), data
