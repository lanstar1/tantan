"""
ClassIn Teacher Portal v2.1 - Persistent Storage
"""
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import hashlib, secrets

from classin_client import (
    test_connection, call_v1, call_v2, parse_v1,
    register_user, add_teacher, add_student, edit_teacher, edit_student,
    create_course, create_class, delete_class,
    add_course_student, add_course_teacher,
    get_login_link, verify_webhook_safe_key, update_class_student_comment,
)
import db

app = FastAPI(title="ClassIn Teacher Portal", version="2.1.0")
sessions = {}  # {token: {username, role, classInUid, displayName}} — sessions are in-memory (OK)

def _hash(pw): return hashlib.sha256(pw.encode()).hexdigest()

@app.on_event("startup")
def startup(): db.init_db()

# ── Auth helpers ─────────────────────────────────
def get_session(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    return sessions.get(token)

def require_auth(request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401, "로그인이 필요합니다.")
    return s

def require_admin(request: Request):
    s = require_auth(request)
    if s["role"] != "admin": raise HTTPException(403, "관리자 권한이 필요합니다.")
    return s

def _creds():
    sid, secret = db.get_creds()
    if not sid or not secret: raise HTTPException(400, "API 키가 설정되지 않았습니다.")
    return sid, secret

# ── Models ───────────────────────────────────────
class SetupInput(BaseModel):
    username: str; password: str; displayName: str = "관리자"
class LoginInput(BaseModel):
    username: str; password: str
class AccountInput(BaseModel):
    username: str; password: str; displayName: str; classInUid: str = ""
class CredentialInput(BaseModel):
    sid: str; secret: str
class APICallInput(BaseModel):
    action: str; version: str = "v1"; params: Optional[dict] = None
class RegisterInput(BaseModel):
    telephone: str; password: str; nickname: str = ""; role: str = "teacher"
class AddUserInput(BaseModel):
    account: str; name: str
class EditUserInput(BaseModel):
    uid: str; name: str
class CourseInput(BaseModel):
    name: str; teacherUid: Optional[str] = None
class ClassInput(BaseModel):
    courseId: str; className: str; beginTime: int; endTime: int; teacherUid: str; seatNum: int = 6
class CourseStudentInput(BaseModel):
    courseId: str; studentUid: str
class LoginLinkInput(BaseModel):
    uid: str
class FeedbackInput(BaseModel):
    courseId: str; classId: str; teacherUid: str; studentUid: str; comment: str

# ═══ Auth ════════════════════════════════════════
@app.get("/api/auth/status")
async def auth_status():
    return {"initialized": db.has_admin(), "accountCount": len(db.list_accounts())}

@app.post("/api/auth/setup")
async def auth_setup(req: SetupInput):
    if db.has_admin(): raise HTTPException(400, "관리자 계정이 이미 존재합니다.")
    db.set_account(req.username, _hash(req.password), "admin", req.displayName)
    return {"success": True, "message": "관리자 계정 생성 완료"}

@app.post("/api/auth/login")
async def auth_login(req: LoginInput):
    acct = db.get_account(req.username)
    if not acct or acct["password_hash"] != _hash(req.password):
        raise HTTPException(401, "아이디 또는 비밀번호가 일치하지 않습니다.")
    token = secrets.token_hex(32)
    sessions[token] = {"username": acct["username"], "role": acct["role"],
                       "classInUid": acct.get("classInUid", ""), "displayName": acct["displayName"]}
    return {"success": True, "token": token, "role": acct["role"],
            "displayName": acct["displayName"], "classInUid": acct.get("classInUid", "")}

@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    sessions.pop(token, None)
    return {"success": True}

@app.get("/api/auth/me")
async def auth_me(session=Depends(require_auth)):
    return session

# ═══ Admin: Accounts ═════════════════════════════
@app.post("/api/admin/accounts")
async def admin_create_account(req: AccountInput, session=Depends(require_admin)):
    if db.get_account(req.username): raise HTTPException(400, "이미 존재하는 아이디입니다.")
    db.set_account(req.username, _hash(req.password), "teacher", req.displayName, req.classInUid)
    return {"success": True, "message": f"강사 계정 생성: {req.displayName}"}

@app.get("/api/admin/accounts")
async def admin_list_accounts(session=Depends(require_admin)):
    return {"accounts": db.list_accounts()}

@app.delete("/api/admin/accounts/{username}")
async def admin_delete_account(username: str, session=Depends(require_admin)):
    if username == session["username"]: raise HTTPException(400, "자신의 계정은 삭제할 수 없습니다.")
    if not db.get_account(username): raise HTTPException(404, "계정을 찾을 수 없습니다.")
    db.del_account(username)
    to_del = [t for t, s in sessions.items() if s["username"] == username]
    for t in to_del: del sessions[t]
    return {"success": True}

# ═══ Stage 1: Connection ═════════════════════════
@app.post("/api/credentials")
async def save_credentials(cred: CredentialInput, session=Depends(require_admin)):
    db.set_creds(cred.sid.strip(), cred.secret.strip())
    return {"success": True, "message": "저장 완료"}

@app.get("/api/credentials/status")
async def get_credential_status(session=Depends(require_auth)):
    sid, _ = db.get_creds()
    return {"configured": bool(sid), "sid": sid[:4]+"****" if sid else None}

@app.post("/api/test-connection")
async def api_test_connection(session=Depends(require_admin)):
    sid, secret = _creds()
    return await test_connection(sid, secret)

@app.post("/api/call")
async def api_call(req: APICallInput, session=Depends(require_admin)):
    sid, secret = _creds()
    try:
        fn = call_v2 if req.version == "v2" else call_v1
        return {"success": True, "data": await fn(req.action, sid, secret, req.params)}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ═══ Stage 2: Users ══════════════════════════════
@app.post("/api/users/register")
async def api_register_user(req: RegisterInput, session=Depends(require_admin)):
    sid, secret = _creds()
    result = await register_user(sid, secret, req.telephone, req.password, req.nickname, 2 if req.role=="teacher" else 1)
    errno, error, data = parse_v1(result)
    uid = str(data) if data else ""
    if errno in [1, 135]:
        db.set_user(uid, req.telephone, req.nickname or req.telephone, req.role)
        return {"success": True, "message": "등록 성공!" if errno==1 else f"기존 계정 (UID:{uid})", "uid": uid, "raw": result}
    return {"success": False, "message": f"실패 ({errno}): {error}", "raw": result}

@app.post("/api/teachers/add")
async def api_add_teacher(req: AddUserInput, session=Depends(require_admin)):
    result = await add_teacher(*_creds(), req.account, req.name)
    e, err, _ = parse_v1(result)
    return {"success": e==1, "message": f"{'완료' if e==1 else '실패'}: {err}", "raw": result}

@app.post("/api/students/add")
async def api_add_student(req: AddUserInput, session=Depends(require_admin)):
    result = await add_student(*_creds(), req.account, req.name)
    e, err, _ = parse_v1(result)
    return {"success": e==1, "message": f"{'완료' if e==1 else '실패'}: {err}", "raw": result}

@app.get("/api/users")
async def api_list_users(role: Optional[str] = None, session=Depends(require_auth)):
    users = db.list_users(role)
    return {"users": users, "total": len(users)}

# ═══ Stage 3: Courses & Classes ══════════════════
@app.post("/api/courses/create")
async def api_create_course(req: CourseInput, session=Depends(require_admin)):
    result = await create_course(*_creds(), req.name, req.teacherUid)
    e, err, data = parse_v1(result)
    if e == 1:
        cid = str(data)
        db.set_course(cid, req.name, req.teacherUid or "")
        return {"success": True, "message": f"코스 생성 (ID:{cid})", "courseId": cid, "raw": result}
    return {"success": False, "message": f"실패 ({e}): {err}", "raw": result}

@app.post("/api/classes/create")
async def api_create_class(req: ClassInput, session=Depends(require_admin)):
    result = await create_class(*_creds(), req.courseId, req.className, req.beginTime, req.endTime, req.teacherUid, req.seatNum)
    e, err, data = parse_v1(result)
    if e == 1:
        clsid = str(data)
        db.set_class(clsid, req.courseId, req.className, req.beginTime, req.endTime, req.teacherUid)
        return {"success": True, "message": f"수업 생성 (ID:{clsid})", "classId": clsid, "raw": result}
    return {"success": False, "message": f"실패 ({e}): {err}", "raw": result}

@app.post("/api/classes/delete")
async def api_delete_class(req: dict, session=Depends(require_admin)):
    result = await delete_class(*_creds(), req["courseId"], req["classId"])
    e, err, _ = parse_v1(result)
    if e == 1: db.del_class(req["classId"])
    return {"success": e==1, "message": "삭제" if e==1 else f"실패: {err}", "raw": result}

@app.post("/api/courses/add-student")
async def api_add_course_student(req: CourseStudentInput, session=Depends(require_admin)):
    result = await add_course_student(*_creds(), req.courseId, req.studentUid)
    e, err, _ = parse_v1(result)
    return {"success": e==1, "message": "배정 완료" if e==1 else f"실패: {err}", "raw": result}

@app.post("/api/courses/add-teacher")
async def api_add_course_teacher(req: dict, session=Depends(require_admin)):
    result = await add_course_teacher(*_creds(), req["courseId"], req["teacherUid"])
    e, err, _ = parse_v1(result)
    return {"success": e==1, "message": "배정 완료" if e==1 else f"실패: {err}", "raw": result}

@app.get("/api/courses")
async def api_list_courses(session=Depends(require_auth)):
    tuid = session.get("classInUid") if session["role"]=="teacher" else None
    return {"courses": db.list_courses(tuid), "total": len(db.list_courses(tuid))}

@app.get("/api/classes")
async def api_list_classes(courseId: Optional[str] = None, session=Depends(require_auth)):
    tuid = session.get("classInUid") if session["role"]=="teacher" else None
    cls = db.list_classes(courseId, tuid)
    return {"classes": cls, "total": len(cls)}

# ═══ Stage 4: Login Link ════════════════════════
@app.post("/api/login-link")
async def api_get_login_link(req: LoginLinkInput, session=Depends(require_auth)):
    result = await get_login_link(*_creds(), req.uid)
    e, err, data = parse_v1(result)
    if e == 1: return {"success": True, "url": str(data), "raw": result}
    return {"success": False, "message": f"실패 ({e}): {err}", "raw": result}

# ═══ Stage 5: Webhook ════════════════════════════
@app.post("/api/webhook/classin")
async def webhook_receiver(request: Request):
    try: body = await request.json()
    except: return JSONResponse({"error_info": {"errno": 0, "error": "Invalid JSON"}})
    sid, secret = db.get_creds()
    if secret:
        sk = body.get("SafeKey", "")
        if sk and not verify_webhook_safe_key(secret, body.get("TimeStamp", 0), sk):
            return JSONResponse({"error_info": {"errno": 0, "error": "SafeKey mismatch"}})
    db.add_webhook(body.get("Cmd", "unknown"), body.get("SID"), body)
    return JSONResponse({"error_info": {"errno": 1, "error": "Success"}})

@app.get("/api/webhooks")
async def api_list_webhooks(limit: int = 50, session=Depends(require_auth)):
    wh, total = db.list_webhooks(limit)
    return {"webhooks": wh, "total": total}

# ═══ Stage 6: Feedback & Settlement ══════════════
@app.post("/api/feedback/submit")
async def api_submit_feedback(req: FeedbackInput, session=Depends(require_auth)):
    result = await update_class_student_comment(*_creds(), req.courseId, req.classId, req.teacherUid, req.studentUid, req.comment)
    e, err, _ = parse_v1(result)
    if e == 1: db.add_feedback(req.courseId, req.classId, req.teacherUid, req.studentUid, req.comment)
    return {"success": e==1, "message": "피드백 제출 완료" if e==1 else f"실패: {err}", "raw": result}

@app.get("/api/feedbacks")
async def api_list_feedbacks(teacherUid: Optional[str] = None, session=Depends(require_auth)):
    tuid = session.get("classInUid") if session["role"]=="teacher" else teacherUid
    fb = db.list_feedbacks(tuid)
    return {"feedbacks": fb, "total": len(fb)}

@app.get("/api/settlement")
async def api_settlement(teacherUid: Optional[str] = None, session=Depends(require_auth)):
    uid = session.get("classInUid") if session["role"]=="teacher" else teacherUid
    cls = db.list_classes(teacher_uid=uid)
    mins = sum((c["end"] - c["begin"]) / 60 for c in cls)
    return {"teacherUid": uid, "totalClasses": len(cls), "totalHours": round(mins/60, 1), "classes": cls}

@app.get("/api/dashboard")
async def api_dashboard(session=Depends(require_auth)):
    return db.count_all()

# ═══ Static ══════════════════════════════════════
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index(): return FileResponse("static/index.html")
