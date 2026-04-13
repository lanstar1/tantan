#!/usr/bin/env python3
"""ClassIn 강사 포털 - 원클릭 실행"""
import subprocess,sys,time,webbrowser,threading,os
PORT=8080
def install():
    try: import fastapi,uvicorn,httpx
    except ImportError: subprocess.check_call([sys.executable,"-m","pip","install","-q","fastapi","uvicorn","httpx","pydantic"])
if __name__=="__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    install()
    print(f"\n  ClassIn 강사 포털 v3.0\n  http://localhost:{PORT}\n  Ctrl+C 종료\n")
    threading.Thread(target=lambda:(time.sleep(2),webbrowser.open(f"http://localhost:{PORT}")),daemon=True).start()
    import uvicorn; uvicorn.run("main:app",host="0.0.0.0",port=PORT,log_level="info")
