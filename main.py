"""
ClassIn Teacher Portal v2.0 - With Auth System
"""
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import json, hashlib, secrets

from classin_client import (
    test_connection, call_v1, call_v2, parse_v1,
    register_user, add_teacher, add_student, edit_teacher, edit_student,
    create_course, create_class, delete_class, edit_class,
    add_course_student, del_course_student, add_course_teacher,
    get_login_link, verify_webhook_safe_key, update_class_student_comment,
)

app = FastAPI(title="ClassIn Teacher Portal", version="2.0.0")

# ═══════════════════════════════════════════════════════════════════
# Stores
# ═══════════════════════════════════════════════════════════════════
credentials = {"sid": None, "secret": None}

# Portal accounts: {username: {username, password_hash, role, displayName, classInUid, created}}
accounts_db = {}
# Sessions: {token: {username, role, classInUid, displayName}}
sessions_db = {}

users_db = {}       # ClassIn users
courses_db = {}
classes_db = {}
webhooks_db = []
feedbacks_db = []

def _hash(pw): return hashlib.sha256(pw.encode()).hexdigest()

# ═══════════════════════════════════════════════════════════════════
# Auth Helpers
# ═══════════════════════════════════════════════════════════════════
def get_session(request: Request) -> Optional[dict]:
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    return sessions_db.get(token)

def require_auth(request: Request) -> dict:
    s = get_session(request)
    if not s:
        raise HTTPException(401, "로그인이 필요합니다.")
    return s

def require_admin(request: Request) -> dict:
    s = require_auth(request)
    if s["role"] != "admin":
        raise HTTPException(403, "관리자 권한이 필요합니다.")
    return s

def _creds():
    if not credentials["sid"] or not credentials["secret"]:
        raise HTTPException(400, "API 키가 설정되지 않았습니다.")
    return credentials["sid"], credentials["secret"]

def _ok(result):
    return parse_v1(result)

# ═══════════════════════════════════════════════════════════════════
# Auth Models
# ═══════════════════════════════════════════════════════════════════
class SetupInput(BaseModel):
    username: str
    password: str
    displayName: str = "관리자"

class LoginInput(BaseModel):
    username: str
    password: str

class AccountInput(BaseModel):
    username: str
    password: str
    displayName: str
    classInUid: str = ""

# ═══════════════════════════════════════════════════════════════════
# Auth Endpoints
# ═══════════════════════════════════════════════════════════════════
@app.get("/api/auth/status")
async def auth_status():
    """Check if initial setup is done and if any session exists"""
    has_admin = any(a["role"] == "admin" for a in accounts_db.values())
    return {"initialized": has_admin, "accountCount": len(accounts_db)}

@app.post("/api/auth/setup")
async def auth_setup(req: SetupInput):
    """First-time admin account creation"""
    if any(a["role"] == "admin" for a in accounts_db.values()):
        raise HTTPException(400, "관리자 계정이 이미 존재합니다.")
    accounts_db[req.username] = {
        "username": req.username,
        "password_hash": _hash(req.password),
        "role": "admin",
        "displayName": req.displayName,
        "classInUid": "",
        "created": datetime.now().isoformat(),
    }
    return {"success": True, "message": "관리자 계정 생성 완료"}

@app.post("/api/auth/login")
async def auth_login(req: LoginInput):
    acct = accounts_db.get(req.username)
    if not acct or acct["password_hash"] != _hash(req.password):
        raise HTTPException(401, "아이디 또는 비밀번호가 일치하지 않습니다.")
    token = secrets.token_hex(32)
    sessions_db[token] = {
        "username": acct["username"],
        "role": acct["role"],
        "classInUid": acct.get("classInUid", ""),
        "displayName": acct["displayName"],
    }
    return {
        "success": True, "token": token,
        "role": acct["role"],
        "displayName": acct["displayName"],
        "classInUid": acct.get("classInUid", ""),
    }

@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    sessions_db.pop(token, None)
    return {"success": True}

@app.get("/api/auth/me")
async def auth_me(session=Depends(require_auth)):
    return session

# ═══════════════════════════════════════════════════════════════════
# Admin: Account Management
# ═══════════════════════════════════════════════════════════════════
@app.post("/api/admin/accounts")
async def admin_create_account(req: AccountInput, session=Depends(require_admin)):
    if req.username in accounts_db:
        raise HTTPException(400, "이미 존재하는 아이디입니다.")
    accounts_db[req.username] = {
        "username": req.username,
        "password_hash": _hash(req.password),
        "role": "teacher",
        "displayName": req.displayName,
        "classInUid": req.classInUid,
        "created": datetime.now().isoformat(),
    }
    return {"success": True, "message": f"강사 계정 생성: {req.displayName}"}

@app.get("/api/admin/accounts")
async def admin_list_accounts(session=Depends(require_admin)):
    return {"accounts": [
        {k: v for k, v in a.items() if k != "password_hash"}
        for a in accounts_db.values()
    ]}

@app.delete("/api/admin/accounts/{username}")
async def admin_delete_account(username: str, session=Depends(require_admin)):
    if username == session["username"]:
        raise HTTPException(400, "자신의 계정은 삭제할 수 없습니다.")
    if username not in accounts_db:
        raise HTTPException(404, "계정을 찾을 수 없습니다.")
    del accounts_db[username]
    # Remove active sessions
    to_remove = [t for t, s in sessions_db.items() if s["username"] == username]
    for t in to_remove:
        del sessions_db[t]
    return {"success": True, "message": f"{username} 삭제 완료"}

# ═══════════════════════════════════════════════════════════════════
# Stage 1: Connection (admin only)
# ═══════════════════════════════════════════════════════════════════
class CredentialInput(BaseModel):
    sid: str
    secret: str

class APICallInput(BaseModel):
    action: str
    version: str = "v1"
    params: Optional[dict] = None

@app.post("/api/credentials")
async def save_credentials(cred: CredentialInput, session=Depends(require_admin)):
    credentials["sid"] = cred.sid.strip()
    credentials["secret"] = cred.secret.strip()
    return {"success": True, "message": "저장 완료"}

@app.get("/api/credentials/status")
async def get_credential_status(session=Depends(require_auth)):
    ok = bool(credentials["sid"] and credentials["secret"])
    return {"configured": ok, "sid": credentials["sid"][:4]+"****" if ok else None}

@app.post("/api/test-connection")
async def api_test_connection(session=Depends(require_admin)):
    sid, secret = _creds()
    return await test_connection(sid, secret)

@app.post("/api/call")
async def api_call(req: APICallInput, session=Depends(require_admin)):
    sid, secret = _creds()
    try:
        fn = call_v2 if req.version == "v2" else call_v1
        result = await fn(req.action, sid, secret, req.params)
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ═══════════════════════════════════════════════════════════════════
# Stage 2: User Management (admin only)
# ═══════════════════════════════════════════════════════════════════
class RegisterInput(BaseModel):
    telephone: str
    password: str
    nickname: str = ""
    role: str = "teacher"

class AddUserInput(BaseModel):
    account: str
    name: str

class EditUserInput(BaseModel):
    uid: str
    name: str

@app.post("/api/users/register")
async def api_register_user(req: RegisterInput, session=Depends(require_admin)):
    sid, secret = _creds()
    add_to = 2 if req.role == "teacher" else 1
    result = await register_user(sid, secret, req.telephone, req.password, req.nickname, add_to)
    errno, error, data = _ok(result)
    uid = str(data) if data else ""
    if errno in [1, 135]:
        users_db[uid] = {"uid": uid, "telephone": req.telephone,
                         "nickname": req.nickname or req.telephone, "role": req.role, "status": "active"}
        return {"success": True, "message": "등록 성공!" if errno == 1 else f"기존 계정 (UID:{uid})", "uid": uid, "raw": result}
    return {"success": False, "message": f"실패 ({errno}): {error}", "raw": result}

@app.post("/api/teachers/add")
async def api_add_teacher(req: AddUserInput, session=Depends(require_admin)):
    sid, secret = _creds()
    result = await add_teacher(sid, secret, req.account, req.name)
    errno, error, _ = _ok(result)
    return {"success": errno == 1, "message": f"{'완료' if errno==1 else '실패'}: {error}", "raw": result}

@app.post("/api/students/add")
async def api_add_student(req: AddUserInput, session=Depends(require_admin)):
    sid, secret = _creds()
    result = await add_student(sid, secret, req.account, req.name)
    errno, error, _ = _ok(result)
    return {"success": errno == 1, "message": f"{'완료' if errno==1 else '실패'}: {error}", "raw": result}

@app.post("/api/teachers/edit")
async def api_edit_teacher(req: EditUserInput, session=Depends(require_admin)):
    sid, secret = _creds()
    result = await edit_teacher(sid, secret, req.uid, req.name)
    errno, _, _ = _ok(result)
    if errno == 1 and req.uid in users_db: users_db[req.uid]["nickname"] = req.name
    return {"success": errno == 1, "raw": result}

@app.post("/api/students/edit")
async def api_edit_student(req: EditUserInput, session=Depends(require_admin)):
    sid, secret = _creds()
    result = await edit_student(sid, secret, req.uid, req.name)
    errno, _, _ = _ok(result)
    if errno == 1 and req.uid in users_db: users_db[req.uid]["nickname"] = req.name
    return {"success": errno == 1, "raw": result}

@app.get("/api/users")
async def api_list_users(role: Optional[str] = None, session=Depends(require_auth)):
    users = list(users_db.values())
    if role: users = [u for u in users if u["role"] == role]
    return {"users": users, "total": len(users)}

# ═══════════════════════════════════════════════════════════════════
# Stage 3: Course & Class (admin creates, teachers view own)
# ═══════════════════════════════════════════════════════════════════
class CourseInput(BaseModel):
    name: str
    teacherUid: Optional[str] = None

class ClassInput(BaseModel):
    courseId: str
    className: str
    beginTime: int
    endTime: int
    teacherUid: str
    seatNum: int = 6

class CourseStudentInput(BaseModel):
    courseId: str
    studentUid: str

@app.post("/api/courses/create")
async def api_create_course(req: CourseInput, session=Depends(require_admin)):
    sid, secret = _creds()
    result = await create_course(sid, secret, req.name, req.teacherUid)
    errno, error, data = _ok(result)
    if errno == 1:
        cid = str(data)
        courses_db[cid] = {"courseId": cid, "name": req.name, "teacherUid": req.teacherUid or "", "classes": []}
        return {"success": True, "message": f"코스 생성 (ID:{cid})", "courseId": cid, "raw": result}
    return {"success": False, "message": f"실패 ({errno}): {error}", "raw": result}

@app.post("/api/classes/create")
async def api_create_class(req: ClassInput, session=Depends(require_admin)):
    sid, secret = _creds()
    result = await create_class(sid, secret, req.courseId, req.className, req.beginTime, req.endTime, req.teacherUid, req.seatNum)
    errno, error, data = _ok(result)
    if errno == 1:
        clsid = str(data)
        cls_data = {"classId": clsid, "courseId": req.courseId, "name": req.className,
                    "begin": req.beginTime, "end": req.endTime, "teacherUid": req.teacherUid}
        classes_db[clsid] = cls_data
        if req.courseId in courses_db: courses_db[req.courseId]["classes"].append(clsid)
        return {"success": True, "message": f"수업 생성 (ID:{clsid})", "classId": clsid, "raw": result}
    return {"success": False, "message": f"실패 ({errno}): {error}", "raw": result}

@app.post("/api/classes/delete")
async def api_delete_class(req: dict, session=Depends(require_admin)):
    sid, secret = _creds()
    result = await delete_class(sid, secret, req["courseId"], req["classId"])
    errno, error, _ = _ok(result)
    if errno == 1: classes_db.pop(req["classId"], None)
    return {"success": errno == 1, "message": "삭제 완료" if errno == 1 else f"실패: {error}", "raw": result}

@app.post("/api/courses/add-student")
async def api_add_course_student(req: CourseStudentInput, session=Depends(require_admin)):
    sid, secret = _creds()
    result = await add_course_student(sid, secret, req.courseId, req.studentUid)
    errno, error, _ = _ok(result)
    return {"success": errno == 1, "message": "배정 완료" if errno == 1 else f"실패: {error}", "raw": result}

@app.post("/api/courses/add-teacher")
async def api_add_course_teacher(req: dict, session=Depends(require_admin)):
    sid, secret = _creds()
    result = await add_course_teacher(sid, secret, req["courseId"], req["teacherUid"])
    errno, error, _ = _ok(result)
    return {"success": errno == 1, "message": "배정 완료" if errno == 1 else f"실패: {error}", "raw": result}

@app.get("/api/courses")
async def api_list_courses(session=Depends(require_auth)):
    courses = list(courses_db.values())
    # Teacher: only own courses
    if session["role"] == "teacher" and session.get("classInUid"):
        courses = [c for c in courses if c["teacherUid"] == session["classInUid"]]
    return {"courses": courses, "total": len(courses)}

@app.get("/api/classes")
async def api_list_classes(courseId: Optional[str] = None, session=Depends(require_auth)):
    cls = list(classes_db.values())
    if courseId: cls = [c for c in cls if c["courseId"] == courseId]
    if session["role"] == "teacher" and session.get("classInUid"):
        cls = [c for c in cls if c["teacherUid"] == session["classInUid"]]
    return {"classes": cls, "total": len(cls)}

# ═══════════════════════════════════════════════════════════════════
# Stage 4: Login Link
# ═══════════════════════════════════════════════════════════════════
class LoginLinkInput(BaseModel):
    uid: str

@app.post("/api/login-link")
async def api_get_login_link(req: LoginLinkInput, session=Depends(require_auth)):
    sid, secret = _creds()
    result = await get_login_link(sid, secret, req.uid)
    errno, error, data = _ok(result)
    if errno == 1:
        return {"success": True, "url": str(data), "raw": result}
    return {"success": False, "message": f"실패 ({errno}): {error}", "raw": result}

# ═══════════════════════════════════════════════════════════════════
# Stage 5: Webhook (no auth - ClassIn calls this)
# ═══════════════════════════════════════════════════════════════════
@app.post("/api/webhook/classin")
async def webhook_receiver(request: Request):
    try: body = await request.json()
    except: return JSONResponse({"error_info": {"errno": 0, "error": "Invalid JSON"}})
    if credentials["secret"]:
        ts = body.get("TimeStamp", 0)
        sk = body.get("SafeKey", "")
        if sk and not verify_webhook_safe_key(credentials["secret"], ts, sk):
            return JSONResponse({"error_info": {"errno": 0, "error": "SafeKey mismatch"}})
    webhooks_db.append({"timestamp": datetime.now().isoformat(), "cmd": body.get("Cmd", "unknown"), "sid": body.get("SID"), "data": body})
    if len(webhooks_db) > 500: webhooks_db[:] = webhooks_db[-500:]
    return JSONResponse({"error_info": {"errno": 1, "error": "Success"}})

@app.get("/api/webhooks")
async def api_list_webhooks(limit: int = 50, session=Depends(require_auth)):
    return {"webhooks": webhooks_db[-limit:], "total": len(webhooks_db)}

# ═══════════════════════════════════════════════════════════════════
# Stage 6: Feedback & Settlement
# ═══════════════════════════════════════════════════════════════════
class FeedbackInput(BaseModel):
    courseId: str
    classId: str
    teacherUid: str
    studentUid: str
    comment: str

@app.post("/api/feedback/submit")
async def api_submit_feedback(req: FeedbackInput, session=Depends(require_auth)):
    sid, secret = _creds()
    result = await update_class_student_comment(sid, secret, req.courseId, req.classId, req.teacherUid, req.studentUid, req.comment)
    errno, error, _ = _ok(result)
    if errno == 1:
        feedbacks_db.append({"courseId": req.courseId, "classId": req.classId,
            "teacherUid": req.teacherUid, "studentUid": req.studentUid,
            "comment": req.comment, "date": datetime.now().isoformat()})
    return {"success": errno == 1, "message": "피드백 제출 완료" if errno == 1 else f"실패: {error}", "raw": result}

@app.get("/api/feedbacks")
async def api_list_feedbacks(teacherUid: Optional[str] = None, session=Depends(require_auth)):
    fb = feedbacks_db
    # Teacher: only own feedback
    if session["role"] == "teacher" and session.get("classInUid"):
        fb = [f for f in fb if f["teacherUid"] == session["classInUid"]]
    elif teacherUid:
        fb = [f for f in fb if f["teacherUid"] == teacherUid]
    return {"feedbacks": fb, "total": len(fb)}

@app.get("/api/settlement")
async def api_settlement(teacherUid: Optional[str] = None, session=Depends(require_auth)):
    cls = list(classes_db.values())
    # Teacher: only own classes
    uid = teacherUid
    if session["role"] == "teacher" and session.get("classInUid"):
        uid = session["classInUid"]
    if uid:
        cls = [c for c in cls if c["teacherUid"] == uid]
    total_mins = sum((c["end"] - c["begin"]) / 60 for c in cls)
    return {"teacherUid": uid, "totalClasses": len(cls), "totalHours": round(total_mins / 60, 1), "classes": cls}

@app.get("/api/dashboard")
async def api_dashboard(session=Depends(require_auth)):
    return {
        "teachers": len([u for u in users_db.values() if u["role"] == "teacher"]),
        "students": len([u for u in users_db.values() if u["role"] == "student"]),
        "courses": len(courses_db), "classes": len(classes_db),
        "webhooks": len(webhooks_db), "feedbacks": len(feedbacks_db),
    }

# ═══════════════════════════════════════════════════════════════════
# Static
# ═══════════════════════════════════════════════════════════════════
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index():
    return FileResponse("static/index.html")
