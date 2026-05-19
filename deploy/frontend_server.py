#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import os
import urllib.error
import urllib.request


BACKEND_BASE = os.environ.get("GASTRO_BACKEND", "http://127.0.0.1:8000").rstrip("/")


class NoCacheHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path.startswith("/media/"):
            self._proxy_backend()
            return
        return super().do_GET()

    def _proxy_backend(self):
        url = BACKEND_BASE + self.path
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = resp.read()
                self.send_response(resp.getcode())
                content_type = resp.headers.get("Content-Type")
                if content_type:
                    self.send_header("Content-Type", content_type)
                length = resp.headers.get("Content-Length")
                if length:
                    self.send_header("Content-Length", length)
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as err:
            self.send_error(err.code, err.reason)
        except OSError:
            self.send_error(502, "Backend unreachable")

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def main():
    port = int(os.environ.get("FRONTEND_PORT", "8080"))
    directory = os.environ.get("FRONTEND_DIR", "frontend")
    os.chdir(directory)
    server = ThreadingHTTPServer(("0.0.0.0", port), NoCacheHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()

