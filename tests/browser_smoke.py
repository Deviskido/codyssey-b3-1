"""Local fixture only: never written to docs/evidence or counted as AWS proof."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lab', ROOT / 'scripts/lab.py')
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK\n')
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    with tempfile.TemporaryDirectory(prefix='lab-browser-test-') as folder:
        destination = Path(folder)
        runner = lab.Lab('unused-local-test')
        runner.s = {'ip': '127.0.0.1:' + str(server.server_port)}
        with patch.object(lab, 'EVIDENCE', destination):
            runner.capture()
        assert (destination / 'external-health.png').read_bytes().startswith(b'\x89PNG')
        assert (destination / 'browser-trace.zip').is_file()
        print('PASS: local HTTP fixture -> real Chromium -> response assertion, PNG and trace')
finally:
    server.shutdown()
