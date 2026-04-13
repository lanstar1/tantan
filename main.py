"""
ClassIn Teacher Portal - Complete Backend (Stages 1-6)
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import json

from classin_client import (
    test_connection, call_v1, call_v2, parse_v1,
    register_user, add_teacher, add_student, edit_teacher, edit_student,
    create_course, create_class, delete_class, edit_class,
    add_course_student, del_course_student, add_course_teacher,
    get_login_link, verify_webhook_safe_key, update_class_student_comment,
)

app = FastAPI(title="ClassIn Teacher Portal", version="1.0.0")

# ═══════════════════════════════════════════════════════════════════
# In-memory Stores (production → DB)
# ═══════════════════════════════════════════════════════════════════
credentials = {"sid": None, "secret": None}
users_db = {}       # {uid: {uid, telephone, nickname, role, status}}
courses_db = {}     # {courseId: {courseId, name, teacherUid, classes:[]}}
classes_db = {}     # {classId: {classId, courseId, name, begin, end, teacherUid}}
webhooks_db = []    # [{timestamp, cmd, data}]
feedbacks_db = []   # [{courseId, classId, teacherUid, studentUid, comment, date}]

def _creds():
    if not credentials["sid"] or not credentials["secret"]:
        raise HTTPException(400, "API 키가 설정되지 않았습니다.")
    return credentials["sid"], credentials["secret"]

def _ok(result):
    errno, error, data = parse_v1(result)
    return errno, error, data

# ═══════════════════════════════════════════════════════════════════
# Models
# ═══════════════════════════════════════════════════════════════════
class CredentialInput(BaseModel):
    sid: str
    secret: str

class APICallInput(BaseModel):
    action: str
    version: str = "v1"
    params: Optional[dict] = None

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

class CourseInput(BaseModel):
    name: str
    teacherUid: Optional[str] = None

class ClassInput(BaseModel):
    courseId: str
    className: str
    beginTime: int          # unix timestamp
    endTime: int
    teacherUid: str
    seatNum: int = 6

class ClassEditInput(BaseModel):
    courseId: str
    classId: str
    className: Optional[str] = None
    beginTime: Optional[int] = None
    endTime: Optional[int] = None

class CourseStudentInput(BaseModel):
    courseId: str
    studentUid: str

class LoginLinkInput(BaseModel):
    uid: str

class FeedbackInput(BaseModel):
    courseId: str
    classId: str
    teacherUid: str
    studentUid: str
    comment: str

# ═══════════════════════════════════════════════════════════════════
# Stage 1: Connection
# ═══════════════════════════════════════════════════════════════════
@app.post("/api/credentials")
async def save_credentials(cred: CredentialInput):
    credentials["sid"] = cred.sid.strip()
    credentials["secret"] = cred.secret.strip()
    return {"success": True, "message": "저장 완료"}

@app.get("/api/credentials/status")
async def get_credential_status():
    ok = bool(credentials["sid"] and credentials["secret"])
    return {"configured": ok, "sid": credentials["sid"][:4]+"****" if ok else None}

@app.post("/api/test-connection")
async def api_test_connection():
    sid, secret = _creds()
    return await test_connection(sid, secret)

@app.post("/api/call")
async def api_call(req: APICallInput):
    sid, secret = _creds()
    try:
        fn = call_v2 if req.version == "v2" else call_v1
        result = await fn(req.action, sid, secret, req.params)
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ═══════════════════════════════════════════════════════════════════
# Stage 2: User Management
# ═══════════════════════════════════════════════════════════════════
@app.post("/api/users/register")
async def api_register_user(req: RegisterInput):
    sid, secret = _creds()
    add_to = 2 if req.role == "teacher" else 1
    result = await register_user(sid, secret, req.telephone, req.password, req.nickname, add_to)
    errno, error, data = _ok(result)
    uid = str(data) if data else ""
    if errno in [1, 135]:
        users_db[uid] = {"uid": uid, "telephone": req.telephone,
                         "nickname": req.nickname or req.telephone, "role": req.role, "status": "active"}
        msg = "등록 성공!" if errno == 1 else f"기존 계정 (UID: {uid})"
        return {"success": True, "message": msg, "uid": uid, "raw": result}
    return {"success": False, "message": f"실패 ({errno}): {error}", "raw": result}

@app.post("/api/teachers/add")
async def api_add_teacher(req: AddUserInput):
    sid, secret = _creds()
    result = await add_teacher(sid, secret, req.account, req.name)
    errno, error, _ = _ok(result)
    return {"success": errno == 1, "message": f"강사 추가 {'완료' if errno==1 else '실패'}: {error}", "raw": result}

@app.post("/api/students/add")
async def api_add_student(req: AddUserInput):
    sid, secret = _creds()
    result = await add_student(sid, secret, req.account, req.name)
    errno, error, _ = _ok(result)
    return {"success": errno == 1, "message": f"학생 추가 {'완료' if errno==1 else '실패'}: {error}", "raw": result}

@app.post("/api/teachers/edit")
async def api_edit_teacher(req: EditUserInput):
    sid, secret = _creds()
    result = await edit_teacher(sid, secret, req.uid, req.name)
    errno, _, _ = _ok(result)
    if errno == 1 and req.uid in users_db:
        users_db[req.uid]["nickname"] = req.name
    return {"success": errno == 1, "message": "수정 완료" if errno == 1 else "실패", "raw": result}

@app.post("/api/students/edit")
async def api_edit_student(req: EditUserInput):
    sid, secret = _creds()
    result = await edit_student(sid, secret, req.uid, req.name)
    errno, _, _ = _ok(result)
    if errno == 1 and req.uid in users_db:
        users_db[req.uid]["nickname"] = req.name
    return {"success": errno == 1, "message": "수정 완료" if errno == 1 else "실패", "raw": result}

@app.get("/api/users")
async def api_list_users(role: Optional[str] = None):
    users = list(users_db.values())
    if role:
        users = [u for u in users if u["role"] == role]
    return {"users": users, "total": len(users)}

# ═══════════════════════════════════════════════════════════════════
# Stage 3: Course & Class Scheduling
# ═══════════════════════════════════════════════════════════════════
@app.post("/api/courses/create")
async def api_create_course(req: CourseInput):
    sid, secret = _creds()
    result = await create_course(sid, secret, req.name, req.teacherUid)
    errno, error, data = _ok(result)
    if errno == 1:
        cid = str(data)
        courses_db[cid] = {"courseId": cid, "name": req.name, "teacherUid": req.teacherUid or "", "classes": []}
        return {"success": True, "message": f"코스 생성 완료 (ID: {cid})", "courseId": cid, "raw": result}
    return {"success": False, "message": f"실패 ({errno}): {error}", "raw": result}

@app.post("/api/classes/create")
async def api_create_class(req: ClassInput):
    sid, secret = _creds()
    result = await create_class(sid, secret, req.courseId, req.className, req.beginTime, req.endTime, req.teacherUid, req.seatNum)
    errno, error, data = _ok(result)
    if errno == 1:
        clsid = str(data)
        cls_data = {"classId": clsid, "courseId": req.courseId, "name": req.className,
                    "begin": req.beginTime, "end": req.endTime, "teacherUid": req.teacherUid}
        classes_db[clsid] = cls_data
        if req.courseId in courses_db:
            courses_db[req.courseId]["classes"].append(clsid)
        return {"success": True, "message": f"수업 생성 완료 (ID: {clsid})", "classId": clsid, "raw": result}
    return {"success": False, "message": f"실패 ({errno}): {error}", "raw": result}

@app.post("/api/classes/delete")
async def api_delete_class(req: dict):
    sid, secret = _creds()
    result = await delete_class(sid, secret, req["courseId"], req["classId"])
    errno, error, _ = _ok(result)
    if errno == 1:
        classes_db.pop(req["classId"], None)
    return {"success": errno == 1, "message": "삭제 완료" if errno == 1 else f"실패: {error}", "raw": result}

@app.post("/api/courses/add-student")
async def api_add_course_student(req: CourseStudentInput):
    sid, secret = _creds()
    result = await add_course_student(sid, secret, req.courseId, req.studentUid)
    errno, error, _ = _ok(result)
    return {"success": errno == 1, "message": "학생 배정 완료" if errno == 1 else f"실패: {error}", "raw": result}

@app.post("/api/courses/add-teacher")
async def api_add_course_teacher(req: dict):
    sid, secret = _creds()
    result = await add_course_teacher(sid, secret, req["courseId"], req["teacherUid"])
    errno, error, _ = _ok(result)
    return {"success": errno == 1, "message": "강사 배정 완료" if errno == 1 else f"실패: {error}", "raw": result}

@app.get("/api/courses")
async def api_list_courses():
    return {"courses": list(courses_db.values()), "total": len(courses_db)}

@app.get("/api/classes")
async def api_list_classes(courseId: Optional[str] = None):
    cls = list(classes_db.values())
    if courseId:
        cls = [c for c in cls if c["courseId"] == courseId]
    return {"classes": cls, "total": len(cls)}

# ═══════════════════════════════════════════════════════════════════
# Stage 4: Login Link
# ═══════════════════════════════════════════════════════════════════
@app.post("/api/login-link")
async def api_get_login_link(req: LoginLinkInput):
    sid, secret = _creds()
    result = await get_login_link(sid, secret, req.uid)
    errno, error, data = _ok(result)
    if errno == 1:
        url = data if isinstance(data, str) else str(data)
        return {"success": True, "url": url, "raw": result}
    return {"success": False, "message": f"실패 ({errno}): {error}", "raw": result}

# ═══════════════════════════════════════════════════════════════════
# Stage 5: Webhook Receiver
# ═══════════════════════════════════════════════════════════════════
@app.post("/api/webhook/classin")
async def webhook_receiver(request: Request):
    """Receive ClassIn data subscription webhooks"""
    try:
        body = await request.json()
    except:
        return JSONResponse({"error_info": {"errno": 0, "error": "Invalid JSON"}})
    
    # Verify SafeKey if credentials set
    if credentials["secret"]:
        ts = body.get("TimeStamp", 0)
        sk = body.get("SafeKey", "")
        if sk and not verify_webhook_safe_key(credentials["secret"], ts, sk):
            return JSONResponse({"error_info": {"errno": 0, "error": "SafeKey mismatch"}})
    
    # Store webhook data
    webhooks_db.append({
        "timestamp": datetime.now().isoformat(),
        "cmd": body.get("Cmd", "unknown"),
        "sid": body.get("SID"),
        "data": body,
    })
    
    # Keep last 500
    if len(webhooks_db) > 500:
        webhooks_db[:] = webhooks_db[-500:]
    
    # ClassIn expects this exact response
    return JSONResponse({"error_info": {"errno": 1, "error": "Success"}})

@app.get("/api/webhooks")
async def api_list_webhooks(limit: int = 50):
    return {"webhooks": webhooks_db[-limit:], "total": len(webhooks_db)}

# ═══════════════════════════════════════════════════════════════════
# Stage 6: Feedback & Settlement
# ═══════════════════════════════════════════════════════════════════
@app.post("/api/feedback/submit")
async def api_submit_feedback(req: FeedbackInput):
    sid, secret = _creds()
    result = await update_class_student_comment(
        sid, secret, req.courseId, req.classId, req.teacherUid, req.studentUid, req.comment
    )
    errno, error, _ = _ok(result)
    if errno == 1:
        feedbacks_db.append({
            "courseId": req.courseId, "classId": req.classId,
            "teacherUid": req.teacherUid, "studentUid": req.studentUid,
            "comment": req.comment, "date": datetime.now().isoformat(),
        })
    return {"success": errno == 1, "message": "피드백 제출 완료" if errno == 1 else f"실패: {error}", "raw": result}

@app.get("/api/feedbacks")
async def api_list_feedbacks(teacherUid: Optional[str] = None):
    fb = feedbacks_db
    if teacherUid:
        fb = [f for f in fb if f["teacherUid"] == teacherUid]
    return {"feedbacks": fb, "total": len(fb)}

@app.get("/api/settlement")
async def api_settlement(teacherUid: Optional[str] = None):
    """Calculate settlement based on class data"""
    cls = list(classes_db.values())
    if teacherUid:
        cls = [c for c in cls if c["teacherUid"] == teacherUid]
    
    total_classes = len(cls)
    total_minutes = sum((c["end"] - c["begin"]) / 60 for c in cls)
    total_hours = round(total_minutes / 60, 1)
    
    return {
        "teacherUid": teacherUid,
        "totalClasses": total_classes,
        "totalHours": total_hours,
        "classes": cls,
    }

@app.get("/api/dashboard")
async def api_dashboard():
    return {
        "teachers": len([u for u in users_db.values() if u["role"] == "teacher"]),
        "students": len([u for u in users_db.values() if u["role"] == "student"]),
        "courses": len(courses_db),
        "classes": len(classes_db),
        "webhooks": len(webhooks_db),
        "feedbacks": len(feedbacks_db),
    }

# ═══════════════════════════════════════════════════════════════════
# Static Files
# ═══════════════════════════════════════════════════════════════════
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index():
    return FileResponse("static/index.html")
