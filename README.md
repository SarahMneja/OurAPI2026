# OurAPI2026 — Students and Reports REST API

A RESTful API developed with **Python, Flask, and JWT authentication** for managing students and their academic reports.

## Project Overview

OurAPI2026 is a Web Services project that provides endpoints to create and retrieve student and report records.

The API includes:
- Student management.
- Report management.
- JWT-based authentication.
- Input validation and error handling.
- Relationships between students and their reports.

## Technologies Used

- Python 3.13
- Flask
- PyJWT
- Postman
- Git and GitHub

## Project Structure

```text
OurAPI2026/
│
├── app.py
├── requirements.txt
├── Dockerfile
├── .dockerignore
├── .gitignore
└── README.md
```

## Installation and Setup

### 1. Clone the repository

```bash
git clone YOUR_REPOSITORY_URL
cd OurAPI2026
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

### 3. Activate the virtual environment

Windows:

```bash
.venv\Scripts\activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Run the application

```bash
python app.py
```

The Flask server will run locally at:

`http://127.0.0.1:5000`

## API Endpoints

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| POST | `/login` | Authenticate and obtain tokens |
| POST | `/refresh` | Obtain a new access token |

### Students

| Method | Endpoint | Description |
|---|---|---|
| POST | `/students` | Create a student |
| GET | `/students` | Retrieve all students |
| GET | `/students/<student_id>` | Retrieve a student by ID |
| GET | `/students/<student_id>/reports` | Retrieve a student's reports |

### Reports

| Method | Endpoint | Description |
|---|---|---|
| POST | `/reports` | Create a report |
| GET | `/reports` | Retrieve all reports |
| GET | `/reports/<report_id>` | Retrieve a report by ID |
| GET | `/reports/<report_id>/student` | Retrieve the student linked to a report |

## Business Rules

- Only level-four students can submit reports.
- Single-major students must submit one report.
- Double-major students must submit two reports.
- Accepted report types are `Internship` and `Mini Senior Project`.
- Each report must have three different keywords, ignoring uppercase and lowercase.
- Student retrieval endpoints require a valid access token.
- Access tokens have a limited lifetime and can be renewed using a refresh token.

## Authentication

Demo credentials:

```json
{
  "username": "admin",
  "password": "1234"
}
```

Use the returned access token as a Bearer token when accessing protected endpoints.

## Testing

The API can be tested using Postman by sending HTTP requests to the local Flask server.

## Notes

- This version stores student and report records in Python lists in memory.
- Data is reset when the Flask application restarts.
- The authentication credentials and secret key are demonstration settings and should be changed before real-world deployment.

---

**Web Services Project — OurAPI2026**