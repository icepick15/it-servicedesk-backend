# IT Service Desk — Backend API

Django REST Framework backend for the CRC IT Service Desk.

## Stack
- Python / Django 6
- Django REST Framework
- Simple JWT authentication
- Microsoft SSO (Azure AD)
- SQLite (dev) / PostgreSQL (prod)

## Setup

```bash
cd helpdesk
pip install -r requirements.txt
cp .env.example .env   # fill in your values
python manage.py migrate
python manage.py runserver
```

## Key endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/token/` | Login (email + password) |
| POST | `/api/auth/microsoft/` | Microsoft SSO |
| GET/POST | `/api/issues/` | List / create tickets |
| PATCH | `/api/issues/:id/` | Claim, transfer, resolve, or reopen a ticket |
| GET/POST | `/api/messages/` | Conversation messages |
| GET | `/api/users/` | User list |

## Ticket actions (PATCH `/api/issues/:id/`)

| `action` value | Who can call it | Effect |
|----------------|-----------------|--------|
| `claim` | Any IT admin (ticket must be unassigned) | Sets `assigned_to` to the caller |
| `transfer` | Current assignee only | Reassigns to another IT admin |
| `resolve` | Current assignee only | Marks resolved, sets `resolved_by` |
| *(none)* + `status: pending` | Any admin | Reopens the ticket |

## Deploy

```bash
gcloud app deploy app.yaml
gcloud app logs tail -s default
```
