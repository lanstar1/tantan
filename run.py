#!/usr/bin/env python3
"""ClassIn 강사 포털 - 원클릭 실행"""
import subprocess, sys, time, webbrowser, threading, os

PORT = 8080

def install_deps():
    try: import fastapi, uvicorn, httpx
    except ImportError:
        print("📦 패키지 설치 중...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "fastapi", "uvicorn", "httpx", "pydantic"])

def open_browser():
    time.sleep(2)
    webbrowser.open(f"http://localhost:{PORT}")

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    install_deps()
    print(f"\n  ClassIn 강사 포털 v1.0")
    print(f"  http://localhost:{PORT}")
    print(f"  종료: Ctrl+C\n")
    threading.Thread(target=open_browser, daemon=True).start()
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, log_level="info")
