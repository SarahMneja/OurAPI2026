from flask import Flask, request, jsonify
from datetime import datetime, timedelta, timezone
from functools import wraps
from contextlib import contextmanager
import os
import jwt
import mysql.connector

from db import Database


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

app = Flask(__name__)
app.json.sort_keys = False

SECRET = os.getenv("JWT_SECRET", "change-me-please")
ACCESS_MINUTES = 1
REFRESH_DAYS = 1

USERS = {
    "admin": "1234"
}

REPORT_TYPES = ("Internship", "Mini Senior Project")
REPORT_LEVEL = 4

# Keep False to enforce keyword uniqueness only within each report.
# Set True if keywords must also be unique across all reports.
UNIQUE_ACROSS_REPORTS = False

STUDENT_FIELDS = ("FN", "LN", "DMjr", "Level")
REPORT_FIELDS = (
    "Title",
    "Type",
    "K1",
    "K2",
    "K3",
    "Release_Date"
)
KEYWORD_FIELDS = ("K1", "K2", "K3")


# --------------------------------------------------
# DATABASE CONNECTION
# --------------------------------------------------

@contextmanager
def get_db_connection():
    """
    Opens a database connection and closes it after the operation.
    Uses the Database class defined in db.py.
    """
    database = Database()

    if not database.connect():
        raise RuntimeError("Could not connect to the database.")

    try:
        yield database.db
    finally:
        database.close()


# --------------------------------------------------
# GENERAL HELPERS
# --------------------------------------------------

def error_response(message, status_code):
    return jsonify({"message": message}), status_code


def is_integer(value):
    """
    Checks that a value is an integer but not a boolean.
    In Python, bool is a subclass of int, so we exclude it.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def get_json_body():
    """
    Reads a JSON request body safely.
    Returns None if the request body is not valid JSON.
    """
    return request.get_json(silent=True)


def make_token(username, token_type):
    now = datetime.now(timezone.utc)

    if token_type == "access":
        expiration = now + timedelta(minutes=ACCESS_MINUTES)
    else:
        expiration = now + timedelta(days=REFRESH_DAYS)

    payload = {
        "user": username,
        "type": token_type,
        "exp": expiration
    }

    return jwt.encode(payload, SECRET, algorithm="HS256")


def token_required(token_type="access"):
    """
    Protects routes using JWT authentication.

    Expected header:
    Authorization: Bearer <token>
    """
    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):

            authorization = request.headers.get("Authorization", "")

            if not authorization.startswith("Bearer "):
                return error_response(
                    "A valid Bearer token is required.",
                    401
                )

            token = authorization.split(" ", 1)[1].strip()

            if not token:
                return error_response("Token is missing.", 401)

            try:
                payload = jwt.decode(
                    token,
                    SECRET,
                    algorithms=["HS256"]
                )

                if payload.get("type") != token_type:
                    return error_response(
                        f"A valid {token_type} token is required.",
                        401
                    )

            except jwt.ExpiredSignatureError:
                return error_response("Token has expired.", 401)

            except jwt.InvalidTokenError:
                return error_response("Invalid token.", 401)

            return function(*args, **kwargs)

        return wrapper
    return decorator


# --------------------------------------------------
# STUDENT VALIDATION
# --------------------------------------------------

def validate_student(data):
    """
    Validates the student information.
    All four fields are required.
    """

    if not isinstance(data, dict):
        return "Request body must be a JSON object."

    for field in STUDENT_FIELDS:
        if field not in data:
            return f"Missing required field: {field}"

    if not isinstance(data["FN"], str) or not data["FN"].strip():
        return "FN must be a non-empty string."

    if not isinstance(data["LN"], str) or not data["LN"].strip():
        return "LN must be a non-empty string."

    if not is_integer(data["DMjr"]) or data["DMjr"] not in (0, 1):
        return "DMjr must be either 0 or 1."

    if not is_integer(data["Level"]) or data["Level"] not in (1, 2, 3, 4):
        return "Level must be 1, 2, 3, or 4."

    return None


def student_required_reports(student):
    """
    Returns the number of reports required by a student.

    Only Level 4 students can submit reports.
    Single major: 1 report.
    Double major: 2 reports.
    """

    if student["Level"] != REPORT_LEVEL:
        return 0

    if student["DMjr"] == 0:
        return 1

    return 2


def count_student_reports(cursor, student_id):
    cursor.execute(
        "SELECT COUNT(*) AS total FROM Reports WHERE ID_S = %s",
        (student_id,)
    )

    result = cursor.fetchone()
    return result["total"]


def student_view(cursor, student):
    """
    Returns a student with the number of reports still missing.
    """

    required = student_required_reports(student)
    submitted = count_student_reports(cursor, student["ID_S"])

    return {
        "ID_S": student["ID_S"],
        "FN": student["FN"],
        "LN": student["LN"],
        "DMjr": student["DMjr"],
        "Level": student["Level"],
        "reports_missing": max(required - submitted, 0)
    }


def fetch_student(cursor, student_id):
    cursor.execute(
        """
        SELECT ID_S, FN, LN, DMjr, `Level`
        FROM Students
        WHERE ID_S = %s
        """,
        (student_id,)
    )

    return cursor.fetchone()


def student_name_exists(cursor, first_name, last_name, exclude_id=None):
    """
    Checks for an existing student with the same first and last name.
    The comparison ignores capitalization and surrounding spaces.
    """

    query = """
        SELECT ID_S
        FROM Students
        WHERE LOWER(TRIM(FN)) = LOWER(TRIM(%s))
          AND LOWER(TRIM(LN)) = LOWER(TRIM(%s))
    """

    values = [first_name, last_name]

    if exclude_id is not None:
        query += " AND ID_S != %s"
        values.append(exclude_id)

    cursor.execute(query, tuple(values))

    return cursor.fetchone() is not None


# --------------------------------------------------
# REPORT VALIDATION
# --------------------------------------------------

def validate_report(data):
    """
    Validates report information.
    All report fields are required.
    """

    if not isinstance(data, dict):
        return "Request body must be a JSON object."

    for field in REPORT_FIELDS:
        if field not in data:
            return f"Missing required field: {field}"

    for field in ("Title", "Type", "K1", "K2", "K3"):
        if not isinstance(data[field], str) or not data[field].strip():
            return f"{field} must be a non-empty string."

    # Validate report type without considering capitalization.
    selected_type = data["Type"].strip()

    matching_type = next(
        (
            report_type
            for report_type in REPORT_TYPES
            if report_type.lower() == selected_type.lower()
        ),
        None
    )

    if matching_type is None:
        return (
            "Type must be either "
            "'Internship' or 'Mini Senior Project'."
        )

    # Validate date format.
    if not isinstance(data["Release_Date"], str):
        return "Release_Date must be a string in YYYY-MM-DD format."

    try:
        datetime.strptime(data["Release_Date"], "%Y-%m-%d")
    except ValueError:
        return "Release_Date must follow the YYYY-MM-DD format."

    # Check that the three keywords are different.
    keywords = [
        data[field].strip().lower()
        for field in KEYWORD_FIELDS
    ]

    if len(set(keywords)) != 3:
        return "K1, K2, and K3 must be different."

    # Store the official report type spelling.
    data["Type"] = matching_type

    return None


def validate_report_owner(cursor, student_id, current_report_id=None):
    """
    Checks that the report belongs to a valid student and that
    the student is allowed to submit another report.

    current_report_id is used when updating an existing report.
    """

    if not is_integer(student_id):
        return "ID_S must be an integer."

    student = fetch_student(cursor, student_id)

    if student is None:
        return "Student does not exist."

    if student["Level"] != REPORT_LEVEL:
        return "Only Level 4 students can submit reports."

    required = student_required_reports(student)
    submitted = count_student_reports(cursor, student_id)

    # When updating a report without changing its owner,
    # do not count that report as an additional submission.
    if current_report_id is not None:
        cursor.execute(
            """
            SELECT ID_R
            FROM Reports
            WHERE ID_R = %s AND ID_S = %s
            """,
            (current_report_id, student_id)
        )

        if cursor.fetchone() is not None:
            submitted -= 1

    if submitted >= required:
        return "This student has already submitted the required number of reports."

    return None


def validate_keywords_across_reports(cursor, data, exclude_report_id=None):
    """
    Optional validation: prevents keywords from being reused
    in different reports when UNIQUE_ACROSS_REPORTS is True.
    """

    if not UNIQUE_ACROSS_REPORTS:
        return None

    for keyword_field in KEYWORD_FIELDS:
        keyword = data[keyword_field].strip().lower()

        query = """
            SELECT ID_R
            FROM Reports
            WHERE (
                LOWER(TRIM(K1)) = %s
                OR LOWER(TRIM(K2)) = %s
                OR LOWER(TRIM(K3)) = %s
            )
        """

        values = [keyword, keyword, keyword]

        if exclude_report_id is not None:
            query += " AND ID_R != %s"
            values.append(exclude_report_id)

        cursor.execute(query, tuple(values))

        if cursor.fetchone() is not None:
            return f"The keyword '{data[keyword_field]}' is already used in another report."

    return None


def fetch_report(cursor, report_id):
    cursor.execute(
        """
        SELECT
            ID_R,
            Title,
            `Type`,
            K1,
            K2,
            K3,
            Release_Date,
            ID_S
        FROM Reports
        WHERE ID_R = %s
        """,
        (report_id,)
    )

    report = cursor.fetchone()

    if report is not None and report["Release_Date"] is not None:
        report["Release_Date"] = report["Release_Date"].isoformat()

    return report


# --------------------------------------------------
# DATABASE ERROR HANDLING
# --------------------------------------------------

@app.errorhandler(404)
def not_found(error):
    return error_response("Resource not found.", 404)


@app.errorhandler(405)
def method_not_allowed(error):
    return error_response("Method not allowed for this endpoint.", 405)


@app.errorhandler(500)
def internal_server_error(error):
    app.logger.exception("Internal server error")
    return error_response("An internal server error occurred.", 500)


def database_error(error):
    app.logger.exception("Database operation failed: %s", error)

    return error_response(
        "A database error occurred. Check the server terminal for details.",
        500
    )


# --------------------------------------------------
# AUTHENTICATION ROUTES
# --------------------------------------------------

@app.route("/login", methods=["POST"])
def login():

    data = get_json_body()

    if not isinstance(data, dict):
        return error_response("Request body must be a JSON object.", 400)

    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return error_response(
            "Username and password are required.",
            400
        )

    if USERS.get(username) != password:
        return error_response("Invalid username or password.", 401)

    access_token = make_token(username, "access")
    refresh_token = make_token(username, "refresh")

    return jsonify({
        "message": "Login successful.",
        "access_token": access_token,
        "refresh_token": refresh_token
    }), 200


@app.route("/refresh", methods=["POST"])
def refresh():

    data = get_json_body()

    if not isinstance(data, dict):
        return error_response("Request body must be a JSON object.", 400)

    refresh_token = data.get("refresh_token")

    if not refresh_token:
        return error_response("Refresh token is required.", 400)

    try:
        payload = jwt.decode(
            refresh_token,
            SECRET,
            algorithms=["HS256"]
        )

        if payload.get("type") != "refresh":
            return error_response("A valid refresh token is required.", 401)

        new_access_token = make_token(payload["user"], "access")

        return jsonify({
            "message": "Access token refreshed successfully.",
            "access_token": new_access_token
        }), 200

    except jwt.ExpiredSignatureError:
        return error_response("Refresh token has expired.", 401)

    except jwt.InvalidTokenError:
        return error_response("Invalid refresh token.", 401)


# --------------------------------------------------
# STUDENT ROUTES
# --------------------------------------------------

# CREATE STUDENT
@app.route("/students", methods=["POST"])
def create_student():

    data = get_json_body()

    validation_error = validate_student(data)

    if validation_error:
        return error_response(validation_error, 400)

    try:
        with get_db_connection() as connection:
            cursor = connection.cursor(dictionary=True)

            try:
                if student_name_exists(cursor, data["FN"], data["LN"]):
                    return error_response(
                        "Student with the same Fname and Lname already exists.",
                        409
                    )

                cursor.execute(
                    """
                    INSERT INTO Students (FN, LN, DMjr, `Level`)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        data["FN"].strip(),
                        data["LN"].strip(),
                        data["DMjr"],
                        data["Level"]
                    )
                )

                student_id = cursor.lastrowid
                connection.commit()

                student = fetch_student(cursor, student_id)

                return jsonify(student_view(cursor, student)), 201

            finally:
                cursor.close()

    except (mysql.connector.Error, RuntimeError) as error:
        return database_error(error)


# GET ALL STUDENTS
@app.route("/students", methods=["GET"])
@token_required()
def get_students():

    try:
        with get_db_connection() as connection:
            cursor = connection.cursor(dictionary=True)

            try:
                cursor.execute(
                    """
                    SELECT ID_S, FN, LN, DMjr, `Level`
                    FROM Students
                    ORDER BY ID_S
                    """
                )

                students = cursor.fetchall()

                result = [
                    student_view(cursor, student)
                    for student in students
                ]

                return jsonify(result), 200

            finally:
                cursor.close()

    except (mysql.connector.Error, RuntimeError) as error:
        return database_error(error)


# GET ONE STUDENT
@app.route("/students/<int:student_id>", methods=["GET"])
@token_required()
def get_student(student_id):

    try:
        with get_db_connection() as connection:
            cursor = connection.cursor(dictionary=True)

            try:
                student = fetch_student(cursor, student_id)

                if student is None:
                    return error_response("Student not found.", 404)

                return jsonify(student_view(cursor, student)), 200

            finally:
                cursor.close()

    except (mysql.connector.Error, RuntimeError) as error:
        return database_error(error)


# GET REPORTS OF A STUDENT
@app.route("/students/<int:student_id>/reports", methods=["GET"])
@token_required()
def get_student_reports(student_id):

    try:
        with get_db_connection() as connection:
            cursor = connection.cursor(dictionary=True)

            try:
                student = fetch_student(cursor, student_id)

                if student is None:
                    return error_response("Student not found.", 404)

                cursor.execute(
                    """
                    SELECT
                        ID_R,
                        Title,
                        `Type`,
                        K1,
                        K2,
                        K3,
                        Release_Date,
                        ID_S
                    FROM Reports
                    WHERE ID_S = %s
                    ORDER BY ID_R
                    """,
                    (student_id,)
                )

                reports = cursor.fetchall()

                for report in reports:
                    if report["Release_Date"] is not None:
                        report["Release_Date"] = (
                            report["Release_Date"].isoformat()
                        )

                return jsonify(reports), 200

            finally:
                cursor.close()

    except (mysql.connector.Error, RuntimeError) as error:
        return database_error(error)


# UPDATE STUDENT
@app.route("/students/<int:student_id>", methods=["PUT"])
def update_student(student_id):

    data = get_json_body()

    validation_error = validate_student(data)

    if validation_error:
        return error_response(validation_error, 400)

    try:
        with get_db_connection() as connection:
            cursor = connection.cursor(dictionary=True)

            try:
                student = fetch_student(cursor, student_id)

                if student is None:
                    return error_response("Student not found.", 404)

                if student_name_exists(
                    cursor,
                    data["FN"],
                    data["LN"],
                    exclude_id=student_id
                ):
                    return error_response(
                        "Student with the same Fname and Lname already exists.",
                        409
                    )

                existing_reports = count_student_reports(cursor, student_id)

                if data["Level"] != REPORT_LEVEL and existing_reports > 0:
                    return error_response(
                        "A student with reports cannot be changed to a level other than 4.",
                        400
                    )

                new_required = (
                    1 if data["DMjr"] == 0 else 2
                ) if data["Level"] == REPORT_LEVEL else 0

                if existing_reports > new_required:
                    return error_response(
                        "The student's major cannot be changed because it would make the number of submitted reports invalid.",
                        400
                    )

                cursor.execute(
                    """
                    UPDATE Students
                    SET FN = %s,
                        LN = %s,
                        DMjr = %s,
                        `Level` = %s
                    WHERE ID_S = %s
                    """,
                    (
                        data["FN"].strip(),
                        data["LN"].strip(),
                        data["DMjr"],
                        data["Level"],
                        student_id
                    )
                )

                connection.commit()

                updated_student = fetch_student(cursor, student_id)

                return jsonify(student_view(cursor, updated_student)), 200

            finally:
                cursor.close()

    except (mysql.connector.Error, RuntimeError) as error:
        return database_error(error)


# DELETE STUDENT
@app.route("/students/<int:student_id>", methods=["DELETE"])
def delete_student(student_id):

    try:
        with get_db_connection() as connection:
            cursor = connection.cursor(dictionary=True)

            try:
                student = fetch_student(cursor, student_id)

                if student is None:
                    return error_response("Student not found.", 404)

                cursor.execute(
                    "DELETE FROM Students WHERE ID_S = %s",
                    (student_id,)
                )

                connection.commit()

                return jsonify({
                    "message": "Student and their associated reports deleted successfully."
                }), 200

            finally:
                cursor.close()

    except (mysql.connector.Error, RuntimeError) as error:
        return database_error(error)


# --------------------------------------------------
# REPORT ROUTES
# --------------------------------------------------

# CREATE REPORT
@app.route("/reports", methods=["POST"])
def create_report():

    data = get_json_body()

    validation_error = validate_report(data)

    if validation_error:
        return error_response(validation_error, 400)

    if "ID_S" not in data:
        return error_response("Missing required field: ID_S", 400)

    if not is_integer(data["ID_S"]):
        return error_response("ID_S must be an integer.", 400)

    try:
        with get_db_connection() as connection:
            cursor = connection.cursor(dictionary=True)

            try:
                owner_error = validate_report_owner(
                    cursor,
                    data["ID_S"]
                )

                if owner_error:
                    return error_response(owner_error, 400)

                keyword_error = validate_keywords_across_reports(
                    cursor,
                    data
                )

                if keyword_error:
                    return error_response(keyword_error, 400)

                cursor.execute(
                    """
                    INSERT INTO Reports
                    (
                        Title,
                        `Type`,
                        K1,
                        K2,
                        K3,
                        Release_Date,
                        ID_S
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        data["Title"].strip(),
                        data["Type"],
                        data["K1"].strip(),
                        data["K2"].strip(),
                        data["K3"].strip(),
                        data["Release_Date"],
                        data["ID_S"]
                    )
                )

                report_id = cursor.lastrowid
                connection.commit()

                report = fetch_report(cursor, report_id)

                return jsonify(report), 201

            finally:
                cursor.close()

    except (mysql.connector.Error, RuntimeError) as error:
        return database_error(error)


# GET ALL REPORTS
@app.route("/reports", methods=["GET"])
def get_reports():

    try:
        with get_db_connection() as connection:
            cursor = connection.cursor(dictionary=True)

            try:
                cursor.execute(
                    """
                    SELECT
                        ID_R,
                        Title,
                        `Type`,
                        K1,
                        K2,
                        K3,
                        Release_Date,
                        ID_S
                    FROM Reports
                    ORDER BY ID_R
                    """
                )

                reports = cursor.fetchall()

                for report in reports:
                    if report["Release_Date"] is not None:
                        report["Release_Date"] = (
                            report["Release_Date"].isoformat()
                        )

                return jsonify(reports), 200

            finally:
                cursor.close()

    except (mysql.connector.Error, RuntimeError) as error:
        return database_error(error)


# GET ONE REPORT
@app.route("/reports/<int:report_id>", methods=["GET"])
def get_report(report_id):

    try:
        with get_db_connection() as connection:
            cursor = connection.cursor(dictionary=True)

            try:
                report = fetch_report(cursor, report_id)

                if report is None:
                    return error_response("Report not found.", 404)

                return jsonify(report), 200

            finally:
                cursor.close()

    except (mysql.connector.Error, RuntimeError) as error:
        return database_error(error)


# GET THE STUDENT WHO OWNS A REPORT
@app.route("/reports/<int:report_id>/student", methods=["GET"])
@token_required()
def get_report_student(report_id):

    try:
        with get_db_connection() as connection:
            cursor = connection.cursor(dictionary=True)

            try:
                report = fetch_report(cursor, report_id)

                if report is None:
                    return error_response("Report not found.", 404)

                student = fetch_student(cursor, report["ID_S"])

                if student is None:
                    return error_response("Student not found.", 404)

                return jsonify(student_view(cursor, student)), 200

            finally:
                cursor.close()

    except (mysql.connector.Error, RuntimeError) as error:
        return database_error(error)


# UPDATE REPORT
@app.route("/reports/<int:report_id>", methods=["PUT"])
def update_report(report_id):

    data = get_json_body()

    validation_error = validate_report(data)

    if validation_error:
        return error_response(validation_error, 400)

    if "ID_S" not in data:
        return error_response("Missing required field: ID_S", 400)

    if not is_integer(data["ID_S"]):
        return error_response("ID_S must be an integer.", 400)

    try:
        with get_db_connection() as connection:
            cursor = connection.cursor(dictionary=True)

            try:
                existing_report = fetch_report(cursor, report_id)

                if existing_report is None:
                    return error_response("Report not found.", 404)

                owner_error = validate_report_owner(
                    cursor,
                    data["ID_S"],
                    current_report_id=report_id
                )

                if owner_error:
                    return error_response(owner_error, 400)

                keyword_error = validate_keywords_across_reports(
                    cursor,
                    data,
                    exclude_report_id=report_id
                )

                if keyword_error:
                    return error_response(keyword_error, 400)

                cursor.execute(
                    """
                    UPDATE Reports
                    SET Title = %s,
                        `Type` = %s,
                        K1 = %s,
                        K2 = %s,
                        K3 = %s,
                        Release_Date = %s,
                        ID_S = %s
                    WHERE ID_R = %s
                    """,
                    (
                        data["Title"].strip(),
                        data["Type"],
                        data["K1"].strip(),
                        data["K2"].strip(),
                        data["K3"].strip(),
                        data["Release_Date"],
                        data["ID_S"],
                        report_id
                    )
                )

                connection.commit()

                updated_report = fetch_report(cursor, report_id)

                return jsonify(updated_report), 200

            finally:
                cursor.close()

    except (mysql.connector.Error, RuntimeError) as error:
        return database_error(error)


# DELETE REPORT
@app.route("/reports/<int:report_id>", methods=["DELETE"])
def delete_report(report_id):

    try:
        with get_db_connection() as connection:
            cursor = connection.cursor(dictionary=True)

            try:
                report = fetch_report(cursor, report_id)

                if report is None:
                    return error_response("Report not found.", 404)

                cursor.execute(
                    "DELETE FROM Reports WHERE ID_R = %s",
                    (report_id,)
                )

                connection.commit()

                return jsonify({
                    "message": "Report deleted successfully."
                }), 200

            finally:
                cursor.close()

    except (mysql.connector.Error, RuntimeError) as error:
        return database_error(error)


# --------------------------------------------------
# RUN APPLICATION
# --------------------------------------------------

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )