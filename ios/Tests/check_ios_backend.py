"""Run the production Swift API client against a temporary FastAPI backend.

Run with the backend virtualenv Python on macOS with Xcode command-line tools:
    backend/.venv/bin/python ios/Tests/check_ios_backend.py
Only model inference is replaced by a deterministic fixture; no AI credentials or
network services are used. App preferences and real databases are untouched.
"""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = '''
import time
import uvicorn
from app import main, kb
from app.schemas import FrameObservation, VisibleItem, LensAnswer, UIScreen, UIComponent, Action
kb.record_observation(main.db, FrameObservation(app="YouTube", screen_kind="detail", sensitive=False,
    items=[VisibleItem(kind="video", title="Integration fixture: AI agents", author="Fixture creator",
        url=None, topics=["ai agents"], summary="An isolated integration fixture.")]), time.time())
def fixture_answer(db, question):
    return (LensAnswer(speech="Fixture response.", ui=UIScreen(title="Fixture", components=[
        UIComponent(type="card", title="Integration fixture: AI agents")]), action=Action(kind="none")),
        {"location":"local", "model":"integration-fixture", "ms":0, "images_sent":0, "impressions_sent":0})
main.answer = fixture_answer
uvicorn.run(main.app, host="127.0.0.1", port=int(__import__("os").environ["LENS_TEST_PORT"]), log_level="error")
'''


def main():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="lens-api-check-") as temporary:
        env = dict(os.environ, LENS_FAKE_MODE="false", LENS_DATA_DIR=temporary, PYTHONPATH=str(ROOT / "backend"),
                   LENS_TEST_PORT=str(port), LENS_TEST_URL=f"http://127.0.0.1:{port}")
        with open(Path(temporary) / "backend.log", "w+") as log:
            server = subprocess.Popen([sys.executable, "-c", FIXTURE], env=env, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    if server.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(log.read())
                    try:
                        with urllib.request.urlopen(env["LENS_TEST_URL"] + "/health", timeout=0.3):
                            break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError("Fixture backend did not become ready")
                binary = str(Path(temporary) / "check-api")
                subprocess.run(["xcrun", "swiftc", "-parse-as-library", str(ROOT / "ios/Lens/LensAPI.swift"),
                                str(ROOT / "ios/Tests/LensAPIIntegration.swift"), "-o", binary], check=True)
                subprocess.run([binary], env=env, check=True)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


if __name__ == "__main__":
    main()
