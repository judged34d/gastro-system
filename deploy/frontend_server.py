#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import os


class NoCacheHandler(SimpleHTTPRequestHandler):
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

