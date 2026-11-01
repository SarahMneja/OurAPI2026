"""
Web Services assignment: Students and Reports REST API
Run with:  python app.py
Needs:     pip install flask pyjwt
"""
import logging
import os
import datetime
from functools import wraps

import jwt
from flask import Flask, jsonify, request

# ---------------------------------------------------------------
# 1. SETTINGS
# ---------------------------------------------------------------
app = Flask(__name__)
SECRET = os.environ.get("SECRET", "change-me-please")
ACCESS_MINUTES = float(os.environ.get("ACCESS_MINUTES", "5"))
REFRESH_DAYS = float(os.environ.get("REFRESH_DAYS", "1"))
PORT = int(os.environ.get("PORT", "5000"))

# Logging: every line goes to the screen (docker logs) AND to logs/app.log
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("logs/app.log")],
)
USERS = {"admin": "1234"}        # the only account allowed to log in

# The only allowed report types (typed in any case, stored as written here)
REPORT_TYPES = ("Internship", "Mini Senior Project")

# Keyword rule (K1, K2, K3 are text, compared WITHOUT caring about case):
#   - always: the 3 keywords of one report must all be different
#   - if True: a keyword value may also not be reused by any other report
UNIQUE_ACROSS_REPORTS = False

# ---------------------------------------------------------------
# 2. THE "DATABASE" (two lists in memory)
# ---------------------------------------------------------------
students = []   # each item: ID_S, FN, LN, DMjr, Level
reports = []    # each item: ID_R, Title, Type, K1, K2, K3, Release_Date
next_student_id = 1
next_report_id = 1
report_links = {}   # side table (not part of the Report class): ID_R -> ID_S

REPORT_LEVEL = 4    # only students of this level may have reports

STUDENT_FIELDS = ("FN", "LN", "DMjr", "Level")
REPORT_FIELDS = ("Title", "Type", "K1", "K2", "K3", "Release_Date")
KEYWORDS = ("K1", "K2", "K3")


# ---------------------------------------------------------------
# 3. HELPERS
# ---------------------------------------------------------------
def error(message, code):
    """Build a clear JSON error with a status code, and write it in the log."""
    logging.warning("%s %s -> %s %s", request.method, request.path, code, message)
    return jsonify({"error": message}), code

def is_int(value):
    """True only for real integers (True/False are not accepted)."""
    return isinstance(value, int) and not isinstance(value, bool)


def norm(text):
    """Normal form of a keyword: no spaces around it, lower case."""
    return text.strip().lower()


def make_token(user, kind, delta):
    """Create a signed token. kind is 'access' or 'refresh'."""
    payload = {
        "user": user,
        "type": kind,
        "exp": datetime.datetime.now(datetime.timezone.utc) + delta,
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


def token_required(f):
    """The guard: runs before the route and checks the access token."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return error("Missing token (updated)", 401)
        try:
            data = jwt.decode(auth[7:], SECRET, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return error("Token expired", 401)
        except jwt.InvalidTokenError:
            return error("Invalid token", 401)
        if data.get("type") != "access":
            return error("Wrong token type: use the access token", 401)
        return f(*args, **kwargs)
    return wrapper


def find(items, key, value):
    """Return the first item whose key equals value, or None."""
    for item in items:
        if item[key] == value:
            return item
    return None


# ---------------------------------------------------------------
# 4. VALIDATION (returns a message if something is wrong, else None)
# ---------------------------------------------------------------
def validate_student(data):
    if not isinstance(data, dict):
        return "Body must be valid JSON"

    missing = [f for f in STUDENT_FIELDS if f not in data]
    if missing:
        return f"Missing fields: {', '.join(missing)}"

    for f in ("FN", "LN"):
        if not isinstance(data[f], str) or not data[f].strip():
            return f"{f} must be non-empty text"

    if not is_int(data["DMjr"]) or data["DMjr"] not in (0, 1):
        return "DMjr must be 0 or 1"
    if not is_int(data["Level"]) or data["Level"] not in (1, 2, 3, 4):
        return "Level must be 1, 2, 3 or 4"
    return None


def validate_report(data):
    """Return an error message or None."""
    if not isinstance(data, dict):
        return "Body must be valid JSON"

    missing = [f for f in REPORT_FIELDS if f not in data]
    if missing:
        return f"Missing fields: {', '.join(missing)}"

    for f in ("Title", "Type") + KEYWORDS:
        if not isinstance(data[f], str) or not data[f].strip():
            return f"{f} must be non-empty text"

    wanted = " ".join(data["Type"].split()).lower()
    for t in REPORT_TYPES:
        if t.lower() == wanted:
            data["Type"] = t          # store the official spelling
            break
    else:
        return f"Type must be one of: {', '.join(REPORT_TYPES)}"

    try:
        datetime.datetime.strptime(data["Release_Date"], "%Y-%m-%d")
    except (ValueError, TypeError):
        return "Release_Date must look like YYYY-MM-DD"

    # Keywords: case-insensitive and unique
    mine = [norm(data[k]) for k in KEYWORDS]
    if len(set(mine)) != len(mine):
        return "K1, K2 and K3 must all be different (case is ignored)"

    if UNIQUE_ACROSS_REPORTS:
        for r in reports:
            used = {norm(r[k]) for k in KEYWORDS}
            clash = [k for k in KEYWORDS if norm(data[k]) in used]
            if clash:
                return (f"Keyword '{data[clash[0]]}' is already used by "
                        f"report {r['ID_R']} (case is ignored)")
    return None


def reports_required(student):
    """How many reports a student must submit: 0 below level 4, 1 at level 4,
    2 for a level 4 student with a double major (DMjr = 1)."""
    if student["Level"] != REPORT_LEVEL:
        return 0
    return 2 if student["DMjr"] == 1 else 1


def reports_submitted(student_id):
    """Number of reports linked to this student."""
    return sum(1 for rid, sid in report_links.items()
               if sid == student_id)


def student_view(student):
    """Student as shown to the client: the 5 fields + reports_missing (0, 1 or 2).
    reports_missing is computed each time, so it is never out of date."""
    view = dict(student)
    view["reports_missing"] = max(
        reports_required(student) - reports_submitted(student["ID_S"]), 0)
    return view


def validate_link(data):
    """Every report must belong to an existing student. Returns (msg, code) or None."""
    if "ID_S" not in data:
        return "Missing fields: ID_S (the student this report belongs to)", 400
    if not is_int(data["ID_S"]):
        return "ID_S must be a whole number", 400
    student = find(students, "ID_S", data["ID_S"])
    if student is None:
        return f"Student {data['ID_S']} not found", 404
    if student["Level"] != REPORT_LEVEL:
        return (f"Only level {REPORT_LEVEL} students can have reports "
                f"(student {student['ID_S']} is level {student['Level']})"), 400
    needed = reports_required(student)
    if reports_submitted(student["ID_S"]) >= needed:
        return (f"Student {student['ID_S']} already submitted all "
                f"{needed} required report(s)"), 400
    return None


# ---------------------------------------------------------------
# 5. LOGIN AND REFRESH
# ---------------------------------------------------------------
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "username" not in data or "password" not in data:
        return error("username and password are required", 400)
    if USERS.get(data["username"]) != data["password"]:
        return error("Wrong username or password", 401)
    return jsonify({
        "access_token": make_token(data["username"], "access",
                                   datetime.timedelta(minutes=ACCESS_MINUTES)),
        "refresh_token": make_token(data["username"], "refresh",
                                    datetime.timedelta(days=REFRESH_DAYS)),
    }), 200


@app.route("/refresh", methods=["POST"])
def refresh():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "refresh_token" not in data:
        return error("refresh_token is required", 400)
    try:
        payload = jwt.decode(data["refresh_token"], SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return error("Refresh token expired, please log in again", 401)
    except jwt.InvalidTokenError:
        return error("Invalid refresh token", 401)
    if payload.get("type") != "refresh":
        return error("Wrong token type: use the refresh token", 401)
    new_access = make_token(payload["user"], "access",
                            datetime.timedelta(minutes=ACCESS_MINUTES))
    return jsonify({"access_token": new_access}), 200


# ---------------------------------------------------------------
# 6. STUDENT ROUTES
# ---------------------------------------------------------------
@app.route("/students", methods=["POST"])
def add_student():
    global next_student_id
    data = request.get_json(silent=True)
    problem = validate_student(data)
    if problem:
        return error(problem, 400)
    student = {"ID_S": next_student_id}
    for f in STUDENT_FIELDS:
        student[f] = data[f]
    next_student_id += 1
    students.append(student)
    return jsonify(student_view(student)), 201


@app.route("/students", methods=["GET"])
@token_required
def get_students():
    return jsonify([student_view(s) for s in students]), 200


@app.route("/students/<int:student_id>", methods=["GET"])
@token_required
def get_student(student_id):
    s = find(students, "ID_S", student_id)
    if s is None:
        return error(f"Student {student_id} not found", 404)
    return jsonify(student_view(s)), 200


@app.route("/students/<int:student_id>/reports", methods=["GET"])
@token_required
def get_student_reports(student_id):
    if find(students, "ID_S", student_id) is None:
        return error(f"Student {student_id} not found", 404)
    mine = [r for r in reports if report_links.get(r["ID_R"]) == student_id]
    return jsonify(mine), 200


# ---------------------------------------------------------------
# 7. REPORT ROUTES (no token needed)
# ---------------------------------------------------------------
@app.route("/reports", methods=["POST"])
def add_report():
    global next_report_id
    data = request.get_json(silent=True)
    problem = validate_report(data)
    if problem:
        return error(problem, 400)
    problem = validate_link(data)
    if problem:
        return error(*problem)
    report = {"ID_R": next_report_id}
    for f in REPORT_FIELDS:
        report[f] = data[f]
    report_links[next_report_id] = data["ID_S"]
    next_report_id += 1
    reports.append(report)
    return jsonify(report), 201


@app.route("/reports", methods=["GET"])
def get_reports():
    return jsonify(reports), 200


@app.route("/reports/<int:report_id>", methods=["GET"])
def get_report(report_id):
    r = find(reports, "ID_R", report_id)
    if r is None:
        return error(f"Report {report_id} not found", 404)
    return jsonify(r), 200


@app.route("/reports/<int:report_id>/student", methods=["GET"])
@token_required
def get_report_student(report_id):
    if find(reports, "ID_R", report_id) is None:
        return error(f"Report {report_id} not found", 404)
    owner = find(students, "ID_S", report_links[report_id])
    return jsonify(student_view(owner)), 200


# ---------------------------------------------------------------
# 8. GLOBAL ERROR HANDLERS (clean JSON instead of ugly pages)
# ---------------------------------------------------------------
@app.errorhandler(404)
def not_found(e):
    return error("Route not found", 404)


@app.errorhandler(405)
def method_not_allowed(e):
    return error("Method not allowed for this route", 405)


@app.errorhandler(500)
def server_error(e):
    logging.exception("Unexpected error")
    return error("Internal server error", 500)


# ---------------------------------------------------------------
# 9. START THE SERVER
# ---------------------------------------------------------------
if __name__ == "__main__":
    logging.info("Starting the API on port %s", PORT)
    app.run(host="0.0.0.0", port=PORT, debug=os.environ.get("DEBUG") == "1")