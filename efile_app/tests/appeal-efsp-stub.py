"""Local read-only EFSP code lists for the appellate browser regression.

Run with ``python tests/appeal-efsp-stub.py``. No fee or filing endpoints are
implemented; requests to them fail, so the browser can never submit a filing.
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/jurisdictions/illinois/codes/courts/TAC1/categories"):
            data = [{"code": "21083", "name": "Appeal", "ecfcasetype": "AppellateCase"}]
        elif self.path.startswith("/jurisdictions/massachusetts/codes/courts/appeals:acp/categories"):
            # Captured from the public Suffolk test EFSP endpoint on 2026-10-01.
            data = [
                {"code": "5796", "name": "Appeals Court Panel Cases - Civil", "ecfcasetype": "AppellateCase"},
                {"code": "5797", "name": "Appeals Court Panel Cases - Criminal", "ecfcasetype": "AppellateCase"},
            ]
        elif self.path.startswith("/jurisdictions/illinois/codes/courts/?"):
            data = [
                {"code": "adams", "name": "Adams County"},
                {"code": "cook:law1", "name": "Cook County - Law - District 1 - Chicago"},
                {"code": "TAC1", "name": "Appellate Court - 1st District"},
                {"code": "zdev-test", "name": "Z - test court"},
            ]
        elif self.path.startswith("/jurisdictions/illinois/codes/courts/TAC1/case_types/37653/party_types"):
            data = [
                {"code": "plaintiff", "name": "Plaintiff", "isrequired": "true"},
                {"code": "defendant", "name": "Defendant", "isrequired": "true"},
            ]
        elif self.path.startswith("/jurisdictions/massachusetts/codes/courts/appeals:acp/case_types/7660/party_types"):
            data = [
                {"code": "plaintiff", "name": "Plaintiff", "isrequired": "true"},
                {"code": "defendant", "name": "Defendant", "isrequired": "true"},
            ]
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")
            return

        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string, *args):
        print(format_string % args, flush=True)


if __name__ == "__main__":
    print("Serving read-only appellate EFSP stubs at http://127.0.0.1:8999", flush=True)
    HTTPServer(("127.0.0.1", 8999), Handler).serve_forever()
