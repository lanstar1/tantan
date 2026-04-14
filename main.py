"""ClassIn Teacher Portal v4.0 - Full Features"""
from fastapi import FastAPI, HTTPException, Request, Depends, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional
import hashlib, secrets, io, csv, json
from classin_client import (test_connection, call_v1, call_v2, parse_v1, register_user, add_teacher, add_student,
    create_course, create_class, delete_class, add_course_student, add_course_teacher,
    get_login_link, verify_webhook_safe_key, update_class_student_comment,
    get_top_folder, get_folder_list, get_cloud_list, upload_file_cloud,
    create_folder, rename_file, del_file, rename_folder, del_folder,
    get_webcast_url, add_course_labels, add_class_labels)
import db, os

app = FastAPI(title="ClassIn Teacher Portal", version="3.0.0")

def _h(pw): return hashlib.sha256(pw.encode()).hexdigest()
@app.on_event("startup")
def startup(): db.init_db()

def _auth(request: Request):
    token = request.headers.get("Authorization","").replace("Bearer ","")
    s = db.get_session(token)
    if not s: raise HTTPException(401,"로그인이 필요합니다.")
    return s
def _admin(request: Request):
    s = _auth(request)
    if s["role"]!="admin": raise HTTPException(403,"관리자 권한 필요")
    return s
def _creds():
    sid,secret = db.get_creds()
    if not sid: raise HTTPException(400,"API 키 미설정")
    return sid,secret

# Models
class M(BaseModel): pass
class SetupIn(M): username:str; password:str; displayName:str="관리자"; timezone:str="Asia/Seoul"
class LoginIn(M): username:str; password:str
class AccountIn(M): username:str; password:str; displayName:str; classInUid:str=""; timezone:str="Asia/Seoul"
class PwChangeIn(M): username:str; newPassword:str
class CredIn(M): sid:str; secret:str
class APICallIn(M): action:str; version:str="v1"; params:Optional[dict]=None
class RegIn(M): telephone:str; password:str; nickname:str=""; role:str="teacher"
class AddUserIn(M): account:str; name:str
class CourseIn(M): name:str; teacherUid:Optional[str]=None
class ClassIn_(M): courseId:str; className:str; beginTime:int; endTime:int; teacherUid:str; seatNum:int=6
class CSIn(M): courseId:str; studentUid:str
class LLIn(M): uid:str
class FBIn(M): courseId:str; classId:str; teacherUid:str; studentUid:str; comment:str
class ProfileIn(M): uid:str; topik_level:str=""; purpose:str=""; notes:str=""; native_lang:str=""

# ═══ Auth ════════════════════════════════════════
@app.get("/api/auth/status")
async def auth_status():
    return {"initialized": db.has_admin()}

@app.post("/api/auth/setup")
async def auth_setup(req: SetupIn):
    if db.has_admin(): raise HTTPException(400,"관리자 존재")
    db.set_account(req.username, _h(req.password), "admin", req.displayName, "", req.timezone)
    return {"success":True}

@app.post("/api/auth/login")
async def auth_login(req: LoginIn):
    a = db.get_account(req.username)
    if not a or a["password_hash"]!=_h(req.password): raise HTTPException(401,"인증 실패")
    token = secrets.token_hex(32)
    db.create_session(token, a["username"], a["role"], a.get("classInUid",""), a["displayName"], a.get("timezone","Asia/Seoul"))
    return {"success":True,"token":token,"role":a["role"],"displayName":a["displayName"],
            "classInUid":a.get("classInUid",""),"timezone":a.get("timezone","Asia/Seoul")}

@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    token = request.headers.get("Authorization","").replace("Bearer ","")
    db.delete_session(token); return {"success":True}

@app.get("/api/auth/me")
async def auth_me(s=Depends(_auth)): return s

# ═══ Admin: Accounts ═════════════════════════════
@app.post("/api/admin/accounts")
async def admin_create(req: AccountIn, s=Depends(_admin)):
    if db.get_account(req.username): raise HTTPException(400,"이미 존재")
    db.set_account(req.username, _h(req.password), "teacher", req.displayName, req.classInUid, req.timezone)
    return {"success":True,"message":f"계정 생성: {req.displayName}"}

@app.get("/api/admin/accounts")
async def admin_list(s=Depends(_admin)): return {"accounts": db.list_accounts()}

@app.delete("/api/admin/accounts/{username}")
async def admin_del(username:str, s=Depends(_admin)):
    if username==s["username"]: raise HTTPException(400,"자기 삭제 불가")
    if not db.get_account(username): raise HTTPException(404)
    db.del_account(username); return {"success":True}

@app.post("/api/admin/change-password")
async def admin_change_pw(req: PwChangeIn, s=Depends(_admin)):
    if not db.get_account(req.username): raise HTTPException(404)
    db.update_password(req.username, _h(req.newPassword))
    db.delete_user_sessions(req.username)
    return {"success":True,"message":"비밀번호 변경 완료 (재로그인 필요)"}

@app.post("/api/auth/change-my-password")
async def change_my_pw(req: dict, s=Depends(_auth)):
    a = db.get_account(s["username"])
    if a["password_hash"]!=_h(req.get("currentPassword","")): raise HTTPException(400,"현재 비밀번호 불일치")
    db.update_password(s["username"], _h(req["newPassword"]))
    return {"success":True,"message":"비밀번호 변경 완료"}

# ═══ Credentials ═════════════════════════════════
@app.post("/api/credentials")
async def save_creds(req: CredIn, s=Depends(_admin)):
    db.set_creds(req.sid.strip(),req.secret.strip()); return {"success":True}
@app.get("/api/credentials/status")
async def cred_status(s=Depends(_auth)):
    sid,_=db.get_creds(); return {"configured":bool(sid),"sid":sid[:4]+"****" if sid else None}
@app.post("/api/test-connection")
async def test_conn(s=Depends(_admin)): return await test_connection(*_creds())

@app.post("/api/call")
async def api_call(req: APICallIn, s=Depends(_admin)):
    try:
        fn=call_v2 if req.version=="v2" else call_v1
        return {"success":True,"data":await fn(req.action,*_creds(),req.params)}
    except Exception as e: return {"success":False,"error":str(e)}

# ═══ Users ═══════════════════════════════════════
@app.post("/api/users/register")
async def reg_user(req: RegIn, s=Depends(_admin)):
    result = await register_user(*_creds(), req.telephone, req.password, req.nickname, 2 if req.role=="teacher" else 1)
    e,err,data = parse_v1(result); uid=str(data) if data else ""
    if e in [1,135]:
        db.set_user(uid, req.telephone, req.nickname or req.telephone, req.role)
        return {"success":True,"uid":uid,"raw":result}
    return {"success":False,"message":f"({e}): {err}","raw":result}

@app.get("/api/users")
async def list_users(role:Optional[str]=None, search:str="", page:int=1, s=Depends(_auth)):
    users, total = db.list_users(role, search, page)
    return {"users":users,"total":total,"page":page}

@app.delete("/api/users/{uid}")
async def del_user(uid:str, s=Depends(_admin)):
    db.del_user(uid)
    return {"success":True}

# ═══ Student Profiles ════════════════════════════
@app.get("/api/students/profile/{uid}")
async def get_profile(uid:str, s=Depends(_auth)):
    return db.get_student_profile(uid)
@app.post("/api/students/profile")
async def set_profile(req: ProfileIn, s=Depends(_auth)):
    db.set_student_profile(req.uid, req.topik_level, req.purpose, req.notes, req.native_lang)
    return {"success":True}

# ═══ Courses & Classes ═══════════════════════════
@app.post("/api/courses/create")
async def cr_course(req: CourseIn, s=Depends(_admin)):
    result = await create_course(*_creds(), req.name, req.teacherUid)
    e,err,data=parse_v1(result)
    if e==1: cid=str(data); db.set_course(cid,req.name,req.teacherUid or ""); return {"success":True,"courseId":cid,"raw":result}
    return {"success":False,"message":f"({e}): {err}","raw":result}

@app.delete("/api/courses/{course_id}")
async def del_course(course_id:str, s=Depends(_admin)):
    sid,secret=_creds()
    result = await call_v1("endCourse", sid, secret, {"courseId": course_id})
    db.del_course(course_id)
    return {"success":True,"raw":result}

@app.post("/api/classes/create")
async def cr_class(req: ClassIn_, s=Depends(_admin)):
    result = await create_class(*_creds(), req.courseId, req.className, req.beginTime, req.endTime, req.teacherUid, req.seatNum)
    e,err,data=parse_v1(result)
    if e==1: clid=str(data); db.set_class(clid,req.courseId,req.className,req.beginTime,req.endTime,req.teacherUid); return {"success":True,"classId":clid,"raw":result}
    return {"success":False,"message":f"({e}): {err}","raw":result}

@app.post("/api/classes/delete")
async def del_cls(req:dict, s=Depends(_admin)):
    result = await delete_class(*_creds(), req["courseId"], req["classId"])
    e,_,_=parse_v1(result)
    if e==1: db.del_class(req["classId"])
    return {"success":e==1,"raw":result}

@app.post("/api/courses/add-student")
async def add_cs(req: CSIn, s=Depends(_admin)):
    result = await add_course_student(*_creds(), req.courseId, req.studentUid)
    e,err,_=parse_v1(result); return {"success":e==1,"message":"완료" if e==1 else err}

@app.get("/api/courses")
async def ls_courses(s=Depends(_auth)):
    tuid = s.get("classInUid") if s["role"]=="teacher" else None
    c=db.list_courses(tuid); return {"courses":c,"total":len(c)}

@app.get("/api/classes")
async def ls_classes(courseId:Optional[str]=None, s=Depends(_auth)):
    tuid = s.get("classInUid") if s["role"]=="teacher" else None
    c=db.list_classes(courseId,tuid); return {"classes":c,"total":len(c)}

# ═══ Availability (Teacher Schedule) ═════════════
class AvailInput(BaseModel):
    date: str           # "2026-04-15"
    startTime: str      # "09:00"
    endTime: str        # "12:00"

@app.post("/api/availability")
async def add_avail(req: AvailInput, s=Depends(_auth)):
    """Teacher adds available time slot"""
    uid = s.get("classInUid") or s["username"]
    name = s["displayName"]
    aid = db.add_availability(uid, name, req.date, req.startTime, req.endTime)
    return {"success":True,"id":aid}

@app.get("/api/availability")
async def list_avail(teacherUid:Optional[str]=None, s=Depends(_auth)):
    """List availability - all teachers or filtered"""
    a = db.list_availability(teacherUid)
    return {"slots":a,"total":len(a)}

@app.delete("/api/availability/{aid}")
async def del_avail(aid:int, s=Depends(_auth)):
    db.del_availability(aid)
    return {"success":True}

# ═══ Login Link ══════════════════════════════════
@app.post("/api/login-link")
async def login_link(req: LLIn, s=Depends(_auth)):
    result = await get_login_link(*_creds(), req.uid)
    e,err,data=parse_v1(result)
    if e==1: return {"success":True,"url":str(data)}
    return {"success":False,"message":f"({e}): {err}"}

# ═══ Cloud Drive ═════════════════════════════════
@app.get("/api/cloud/top-folder")
async def cloud_top(s=Depends(_auth)):
    result = await get_top_folder(*_creds())
    e,err,data=parse_v1(result)
    return {"success":e==1,"data":data,"raw":result}

@app.get("/api/cloud/list/{folder_id}")
async def cloud_list(folder_id:str, s=Depends(_auth)):
    result = await get_cloud_list(*_creds(), folder_id)
    e,err,data=parse_v1(result)
    return {"success":e==1,"data":data,"raw":result}

@app.get("/api/cloud/folders/{folder_id}")
async def cloud_folders(folder_id:str, s=Depends(_auth)):
    result = await get_folder_list(*_creds(), folder_id)
    e,err,data=parse_v1(result)
    return {"success":e==1,"data":data,"raw":result}

@app.post("/api/cloud/create-folder")
async def cloud_create_folder(request: Request, s=Depends(_auth)):
    body = await request.json()
    pid = body.get("parentId",""); name = body.get("folderName","")
    if not pid or not name: raise HTTPException(400, "parentId, folderName 필수")
    result = await create_folder(*_creds(), pid, name)
    e,err,data=parse_v1(result)
    return {"success":e==1,"data":data,"message":err,"raw":result}

@app.post("/api/cloud/upload")
async def cloud_upload(folder_id: str = Form(...), file: UploadFile = File(...), s=Depends(_auth)):
    content = await file.read()
    if len(content) > 500*1024*1024: raise HTTPException(400, "파일 크기 500MB 초과")
    result = await upload_file_cloud(*_creds(), folder_id, content, file.filename)
    e,err,data=parse_v1(result)
    return {"success":e==1,"fileId":data,"message":err,"raw":result}

@app.post("/api/cloud/rename-file")
async def cloud_rename_file(request: Request, s=Depends(_auth)):
    body = await request.json()
    result = await rename_file(*_creds(), body.get("fileId",""), body.get("fileName",""))
    e,err,data=parse_v1(result)
    return {"success":e==1,"message":err,"raw":result}

@app.delete("/api/cloud/file/{file_id}")
async def cloud_del_file(file_id:str, s=Depends(_auth)):
    result = await del_file(*_creds(), file_id)
    e,err,data=parse_v1(result)
    return {"success":e==1,"message":err,"raw":result}

@app.post("/api/cloud/rename-folder")
async def cloud_rename_folder(request: Request, s=Depends(_auth)):
    body = await request.json()
    result = await rename_folder(*_creds(), body.get("folderId",""), body.get("folderName",""))
    e,err,data=parse_v1(result)
    return {"success":e==1,"message":err,"raw":result}

@app.delete("/api/cloud/folder/{folder_id}")
async def cloud_del_folder(folder_id:str, s=Depends(_auth)):
    result = await del_folder(*_creds(), folder_id)
    e,err,data=parse_v1(result)
    return {"success":e==1,"message":err,"raw":result}

# ═══ Webhook ═════════════════════════════════════
@app.post("/api/webhook/classin")
async def webhook(request: Request):
    try: body = await request.json()
    except: return JSONResponse({"error_info":{"errno":0,"error":"Invalid JSON"}})
    _,secret = db.get_creds()
    if secret:
        sk=body.get("SafeKey","")
        if sk and not verify_webhook_safe_key(secret,body.get("TimeStamp",0),sk):
            return JSONResponse({"error_info":{"errno":0,"error":"SafeKey mismatch"}})
    db.add_webhook(body.get("Cmd","unknown"),body.get("SID"),body)
    return JSONResponse({"error_info":{"errno":1,"error":"Success"}})

@app.get("/api/webhooks")
async def ls_webhooks(limit:int=50, s=Depends(_auth)):
    wh,total=db.list_webhooks(limit); return {"webhooks":wh,"total":total}

@app.get("/api/webhooks/stats")
async def wh_stats(s=Depends(_auth)):
    return {"stats": db.get_webhook_stats()}

# ═══ Feedback ════════════════════════════════════
@app.post("/api/feedback/submit")
async def submit_fb(req: FBIn, s=Depends(_auth)):
    result = await update_class_student_comment(*_creds(), req.courseId, req.classId, req.teacherUid, req.studentUid, req.comment)
    e,err,_=parse_v1(result)
    if e==1: db.add_feedback(req.courseId,req.classId,req.teacherUid,req.studentUid,req.comment)
    return {"success":e==1,"message":"완료" if e==1 else err}

@app.get("/api/feedbacks")
async def ls_fb(teacherUid:Optional[str]=None, s=Depends(_auth)):
    tuid = s.get("classInUid") if s["role"]=="teacher" else teacherUid
    fb=db.list_feedbacks(tuid); return {"feedbacks":fb,"total":len(fb)}

# ═══ Settlement & Export ═════════════════════════
@app.get("/api/settlement")
async def settlement(teacherUid:Optional[str]=None, s=Depends(_auth)):
    uid = s.get("classInUid") if s["role"]=="teacher" else teacherUid
    cls = db.list_classes(teacher_uid=uid)
    mins=sum((c["end"]-c["begin"])/60 for c in cls)
    return {"teacherUid":uid,"totalClasses":len(cls),"totalHours":round(mins/60,1),"classes":cls}

@app.get("/api/settlement/export")
async def export_csv(teacherUid:Optional[str]=None, s=Depends(_auth)):
    uid = s.get("classInUid") if s["role"]=="teacher" else teacherUid
    cls = db.list_classes(teacher_uid=uid)
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["수업ID","코스ID","수업명","시작(UTC)","종료(UTC)","강사UID","시간(분)"])
    for c in cls:
        w.writerow([c["classId"],c["courseId"],c["name"],c["begin"],c["end"],c["teacherUid"],round((c["end"]-c["begin"])/60)])
    output.seek(0)
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv", headers={"Content-Disposition":"attachment; filename=settlement.csv"})

@app.get("/api/dashboard")
async def dashboard(s=Depends(_auth)): return db.count_all()

# ═══ Upcoming classes (for notifications) ════════
@app.get("/api/classes/upcoming")
async def upcoming(s=Depends(_auth)):
    import time; now=int(time.time())
    tuid = s.get("classInUid") if s["role"]=="teacher" else None
    cls = db.list_classes(teacher_uid=tuid)
    upcoming = [c for c in cls if c["begin"]>now]
    return {"classes": upcoming[:10]}

# ═══ Teacher Profile ═════════════════════════════
@app.get("/api/teacher-profile/{uid}")
async def get_tp(uid:str, s=Depends(_auth)):
    return db.get_teacher_profile(uid)

@app.post("/api/teacher-profile")
async def set_tp(req:dict, s=Depends(_auth)):
    uid = req.get("uid") or s.get("classInUid") or s["username"]
    db.set_teacher_profile(uid, req.get("bio",""), req.get("career",""), req.get("intro_video",""),
        req.get("photo_url",""), req.get("certificates",""), int(req.get("hourly_rate",0)))
    return {"success":True}

# ═══ Announcements ═══════════════════════════════
@app.post("/api/announcements")
async def add_ann(req:dict, s=Depends(_admin)):
    db.add_announcement(req["title"], req["content"], s["displayName"])
    return {"success":True}

@app.get("/api/announcements")
async def ls_ann(s=Depends(_auth)):
    return {"announcements": db.list_announcements()}

@app.delete("/api/announcements/{aid}")
async def del_ann(aid:int, s=Depends(_admin)):
    db.del_announcement(aid); return {"success":True}

# ═══ Inquiries (1:1 문의) ════════════════════════
@app.post("/api/inquiries")
async def add_inq(req:dict, s=Depends(_auth)):
    db.add_inquiry(s["username"], req["subject"], req["content"])
    return {"success":True}

@app.get("/api/inquiries")
async def ls_inq(s=Depends(_auth)):
    user = None if s["role"]=="admin" else s["username"]
    return {"inquiries": db.list_inquiries(user)}

@app.post("/api/inquiries/{iid}/reply")
async def reply_inq(iid:int, req:dict, s=Depends(_admin)):
    db.reply_inquiry(iid, req["reply"])
    return {"success":True}

# ═══ Absences (결석 증빙) ════════════════════════
@app.post("/api/absences")
async def add_abs(req:dict, s=Depends(_auth)):
    uid = s.get("classInUid") or s["username"]
    db.add_absence(uid, req.get("classId",""), req.get("reason",""), req.get("photoUrl",""))
    return {"success":True}

@app.get("/api/absences")
async def ls_abs(s=Depends(_auth)):
    uid = s.get("classInUid") if s["role"]=="teacher" else None
    return {"absences": db.list_absences(uid)}

# ═══ Ratings (만족도/별점) ═══════════════════════
@app.post("/api/ratings")
async def add_rat(req:dict, s=Depends(_auth)):
    db.add_rating(req["classId"], req.get("courseId",""), req.get("studentUid",""),
        req.get("teacherUid",""), int(req.get("score",5)), req.get("review",""))
    return {"success":True}

@app.get("/api/ratings")
async def ls_rat(teacherUid:Optional[str]=None, s=Depends(_auth)):
    tuid = s.get("classInUid") if s["role"]=="teacher" else teacherUid
    return {"ratings": db.list_ratings(tuid)}

@app.get("/api/teacher-stats")
async def teacher_stats(teacherUid:Optional[str]=None, s=Depends(_auth)):
    return {"stats": db.get_teacher_stats(teacherUid)}

# ═══ Enhanced Settlement (수입 포함) ═════════════
@app.get("/api/income")
async def income(s=Depends(_auth)):
    uid = s.get("classInUid") if s["role"]=="teacher" else None
    cls = db.list_classes(teacher_uid=uid)
    profile = db.get_teacher_profile(uid or "") if uid else {"hourly_rate":0}
    rate = profile.get("hourly_rate",0)
    total_mins = sum((c["end"]-c["begin"])/60 for c in cls)
    total_hours = round(total_mins/60,1)
    total_income = round(total_hours * rate)
    return {"teacherUid":uid,"totalClasses":len(cls),"totalHours":total_hours,
            "hourlyRate":rate,"totalIncome":total_income}

# ═══ Curriculum (교육과정) ═══════════════════════
@app.post("/api/curriculum")
async def add_cur(request: Request, s=Depends(_admin)):
    b=await request.json()
    cid=db.add_curriculum(b.get("level",""),b.get("unitNumber",0),b.get("title",""),
        b.get("description",""),json.dumps(b.get("keyPoints",[]),ensure_ascii=False),b.get("materials",""))
    return {"success":True,"id":cid}

@app.get("/api/curriculum")
async def list_cur(level:str=None, s=Depends(_auth)):
    return {"curriculum":db.list_curriculum(level)}

@app.get("/api/curriculum/{cid}")
async def get_cur(cid:int, s=Depends(_auth)):
    c=db.get_curriculum(cid)
    if not c: raise HTTPException(404,"교육과정 없음")
    return c

@app.put("/api/curriculum/{cid}")
async def update_cur(cid:int, request: Request, s=Depends(_admin)):
    b=await request.json()
    db.update_curriculum(cid,b.get("level",""),b.get("unitNumber",0),b.get("title",""),
        b.get("description",""),json.dumps(b.get("keyPoints",[]),ensure_ascii=False),b.get("materials",""))
    return {"success":True}

@app.delete("/api/curriculum/{cid}")
async def del_cur(cid:int, s=Depends(_admin)):
    db.del_curriculum(cid); return {"success":True}

# ═══ Student Progress (학생 진도) ════════════════
@app.post("/api/progress")
async def set_prog(request: Request, s=Depends(_auth)):
    b=await request.json()
    tuid=s.get("classInUid","") if s["role"]=="teacher" else b.get("teacherUid","")
    db.set_progress(b["studentUid"],b["curriculumId"],b.get("status","in_progress"),
        tuid,b.get("notes",""),b.get("courseId",""))
    return {"success":True}

@app.get("/api/progress/{student_uid}")
async def get_prog(student_uid:str, course_id:str=None, s=Depends(_auth)):
    return {"progress":db.get_progress(student_uid,course_id)}

@app.get("/api/my-students-progress")
async def my_students(s=Depends(_auth)):
    uid=s.get("classInUid","")
    if not uid: return {"students":[]}
    return {"students":db.get_teacher_students_progress(uid)}

# ═══ Teaching Guides (수업 지침서) ═══════════════
@app.post("/api/guides")
async def add_gd(request: Request, s=Depends(_auth)):
    b=await request.json()
    gid=db.add_guide(b["curriculumId"],b["content"],b.get("guideType","admin"),
        b.get("targetLang",""),s.get("displayName",""))
    return {"success":True,"id":gid}

@app.get("/api/guides")
async def list_gd(curriculum_id:int=None, s=Depends(_auth)):
    return {"guides":db.list_guides(curriculum_id)}

@app.delete("/api/guides/{gid}")
async def del_gd(gid:int, s=Depends(_admin)):
    db.del_guide(gid); return {"success":True}

@app.post("/api/guides/ai-generate")
async def ai_guide(request: Request, s=Depends(_auth)):
    b=await request.json()
    cur=db.get_curriculum(b.get("curriculumId",0))
    if not cur: raise HTTPException(404,"교육과정 없음")
    student_lang=b.get("targetLang","")
    student_info=b.get("studentInfo","")
    try:
        import httpx
        prompt=f"""한국어 교육 전문가로서, 아래 수업 단원에 대한 강사용 수업 지침서를 작성해주세요.

단원: {cur['title']} (레벨: {cur['level']}, {cur['unitNumber']}과)
단원 설명: {cur.get('description','')}
핵심 포인트: {cur.get('keyPoints','[]')}
{f'학생 모국어: {student_lang}' if student_lang else ''}
{f'학생 정보: {student_info}' if student_info else ''}

다음을 포함해서 작성:
1. 수업 도입 (5분) - 워밍업 활동
2. 핵심 문법/어휘 설명 포인트
3. 연습 활동 제안 (2-3개)
4. {f'{student_lang} 모국어 화자가 자주 실수하는 부분과 대처법' if student_lang else '외국인 학습자가 자주 실수하는 부분'}
5. 수업 마무리 활동

간결하고 실용적으로 작성해주세요."""
        api_key=os.environ.get("ANTHROPIC_API_KEY","")
        if not api_key: return {"success":False,"message":"ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다"}
        async with httpx.AsyncClient(timeout=60) as client:
            resp=await client.post("https://api.anthropic.com/v1/messages",
                headers={"x-api-key":api_key,"anthropic-version":"2023-06-01","content-type":"application/json"},
                json={"model":"claude-sonnet-4-20250514","max_tokens":2000,"messages":[{"role":"user","content":prompt}]})
            data=resp.json()
            content=data.get("content",[{}])[0].get("text","생성 실패")
        gid=db.add_guide(b["curriculumId"],content,"ai",student_lang,s.get("displayName",""))
        return {"success":True,"id":gid,"content":content}
    except Exception as ex:
        return {"success":False,"message":str(ex)}

# ═══ Class Recordings (수업 녹화) ════════════════
@app.post("/api/recordings/fetch")
async def fetch_rec(request: Request, s=Depends(_auth)):
    b=await request.json()
    result=await get_webcast_url(*_creds(),b.get("courseId",""),b.get("classId",""))
    e,err,data=parse_v1(result)
    if e==1 and data:
        replay=data.get("replay_url","") if isinstance(data,dict) else ""
        live=data.get("live_url","") if isinstance(data,dict) else ""
        if isinstance(data,dict) and data.get("live_url"):
            replay=data.get("live_url","")
        db.add_recording(b.get("classId",""),b.get("courseId",""),b.get("className",""),
            replay,live,b.get("teacherUid",""))
        return {"success":True,"data":data,"raw":result}
    return {"success":False,"message":err,"raw":result}

@app.get("/api/recordings")
async def list_rec(featured:bool=False, s=Depends(_auth)):
    tuid=s.get("classInUid","") if s["role"]=="teacher" else None
    return {"recordings":db.list_recordings(tuid,featured)}

@app.post("/api/recordings/{rid}/featured")
async def toggle_feat(rid:int, request: Request, s=Depends(_admin)):
    b=await request.json()
    db.toggle_featured(rid,b.get("featured",False))
    return {"success":True}

# ═══ Labels ══════════════════════════════════════
@app.post("/api/labels/course")
async def label_course(request: Request, s=Depends(_admin)):
    b=await request.json()
    result=await add_course_labels(*_creds(),b.get("courseId",""),b.get("labels",""))
    e,err,data=parse_v1(result)
    return {"success":e==1,"message":err,"raw":result}

@app.post("/api/labels/class")
async def label_class(request: Request, s=Depends(_admin)):
    b=await request.json()
    result=await add_class_labels(*_creds(),b.get("courseId",""),b.get("classId",""),b.get("labels",""))
    e,err,data=parse_v1(result)
    return {"success":e==1,"message":err,"raw":result}

# ═══ Static ══════════════════════════════════════
app.mount("/static", StaticFiles(directory="static"), name="static")
@app.get("/favicon.ico")
async def favicon(): return FileResponse("static/favicon.ico") if __import__("os").path.exists("static/favicon.ico") else JSONResponse(status_code=204,content=None)

@app.get("/")
async def index(): return FileResponse("static/index.html")
