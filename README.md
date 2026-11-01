# OurAPI2026

A Flask REST API for managing students and their academic reports. The
project includes JWT authentication, input validation, and Docker
support.

## Features

-   Create and retrieve students and academic reports.
-   JWT authentication for protected student endpoints.
-   Access-token refresh.
-   Validation of student and report business rules.
-   Custom JSON error responses.
-   Run locally with Python or inside Docker.

## Technologies

-   Python 3.13
-   Flask
-   PyJWT
-   Docker

## Project Structure

``` text
OurAPI2026/
├── app.py
├── Dockerfile
├── .dockerignore
├── requirements.txt
├── README.md
└── .gitignore
```

Your local `.venv/` and generated log/cache files should not be
committed.

## Requirements

For local execution: Python 3.13 (or compatible) and pip.

For Docker execution: Docker Desktop installed and running.

## Run Locally

### 1. Clone the repository

``` bash
git clone <YOUR_REPOSITORY_URL>
cd OurAPI2026
```

### 2. Create and activate a virtual environment

``` bash
python -m venv .venv
```

Windows PowerShell:

``` powershell
.venv\Scripts\Activate.ps1
```

Windows Command Prompt:

``` cmd
.venv\Scripts\activate
```

### 3. Install dependencies

``` bash
pip install -r requirements.txt
```

### 4. Start the API

``` bash
python app.py
```

The API should be available at `http://127.0.0.1:5000`.

## Run with Docker

Make sure Docker Desktop is running. Open a terminal in the project
root, where the `Dockerfile` is located.

### 1. Build the image

``` bash
docker build -t ourapi2026 .
```

### 2. Run a container

``` bash
docker run --name ourapi2026-container -p 5000:5000 ourapi2026
```

The API should then be accessible at `http://localhost:5000`.

**Docker configuration note:** The Flask application inside the
container must listen on `0.0.0.0` and the port exposed by the
Dockerfile (here, `5000`) for this port mapping to work. If the
container starts but the API cannot be reached, check the existing
`Dockerfile` and the Flask run configuration in `app.py`.

### Useful Docker commands

  -------------------------------------------------------------------------
  Command                               Description
  ------------------------------------- -----------------------------------
  `docker images`                       List Docker images

  `docker ps`                           List running containers

  `docker ps -a`                        List all containers, including
                                        stopped ones

  `docker logs ourapi2026-container`    View container logs

  `docker stop ourapi2026-container`    Stop the container

  `docker start ourapi2026-container`   Start the stopped container

  `docker rm ourapi2026-container`      Remove the container after stopping
                                        it

  `docker rmi ourapi2026`               Remove the image
  -------------------------------------------------------------------------

To replace an existing container with a new one:

``` bash
docker stop ourapi2026-container
docker rm ourapi2026-container
```

## API Endpoints

The following endpoints describe the current list-based implementation.

  ----------------------------------------------------------------------------------------
  Method            Endpoint                           Authentication    Description
  ----------------- ---------------------------------- ----------------- -----------------
  `POST`            `/login`                           No                Authenticate and
                                                                         obtain tokens

  `POST`            `/refresh`                         Refresh token     Obtain a new
                                                                         access token

  `POST`            `/students`                        No                Create a student

  `GET`             `/students`                        Access token      Retrieve all
                                                                         students

  `GET`             `/students/<student_id>`           Access token      Retrieve a
                                                                         student by ID

  `GET`             `/students/<student_id>/reports`   Access token      Retrieve reports
                                                                         belonging to a
                                                                         student

  `POST`            `/reports`                         No                Create a report

  `GET`             `/reports`                         No                Retrieve all
                                                                         reports

  `GET`             `/reports/<report_id>`             No                Retrieve a report
                                                                         by ID

  `GET`             `/reports/<report_id>/student`     Access token      Retrieve the
                                                                         student
                                                                         associated with a
                                                                         report
  ----------------------------------------------------------------------------------------

## Business Rules

-   Only Level 4 students can have reports.
-   A single-major student can have one report.
-   A double-major student can have two reports.
-   Accepted report types are `Internship` and `Mini Senior Project`.
-   Each report must contain three different keywords. Keyword
    comparison ignores letter case.

## Authentication

The demonstration credentials configured in the current code are:

``` text
Username: admin
Password: 1234
```

The access token has a short lifetime (1 minute in the current demo
configuration). The refresh token can be used through `/refresh` to
obtain a new access token.

**Security note:** These are demonstration credentials, not production
credentials. Do not commit real passwords, tokens, or private
configuration files to GitHub.

## Data Storage

In the current implementation, students and reports are stored in Python
lists in memory. Data is reset when the application stops or restarts.

The database migration is a separate next step. Once database
persistence is implemented, update this section and the endpoint
documentation to reflect the final database-backed version.

## Testing with Postman

1.  Start the API locally or with Docker.
2.  Send requests to `http://127.0.0.1:5000` (local run) or
    `http://localhost:5000` (Docker).
3.  Test endpoints using the HTTP methods and paths in the API Endpoints
    table.
4.  For protected routes, log in first and send the access token as a
    Bearer token in the `Authorization` header.
5.  Test valid requests and validation/error cases.

## Notes

-   Run commands from the project root unless stated otherwise.
-   Do not commit `.venv/`, `__pycache__/`, log files, or files
    containing secrets.
-   Keep `requirements.txt` updated when dependencies change.
