# Backend

This repository contains the backend API for the AI‑Pallet‑Piler project. It provides data storage, business logic, and algorithmic calculations for the frontend applications.

## Prerequisites

- **Python** 3.9 or newer
- **PostgreSQL** (any recent version)
- **Git** (to clone the repository)
- **Virtual environment** support (`virtualenv`)

### Operating‑system specific requirements

- **Linux** – `apt` (or your distro's package manager) is used in the examples.
- **Windows** – the examples use **Chocolatey** (`choco`). If you prefer the graphical installer, you can download PostgreSQL from the official website.

## Setup

### 1. Install PostgreSQL

#### Linux

```bash
sudo apt update && sudo apt install -y postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

#### Windows (Chocolatey)

```powershell
choco install postgresql -y
# After installation, start the service (it usually starts automatically)
```

If you used the graphical installer, make sure the **PostgreSQL** service is running (you can start it from *Services* or using `pg_ctl`).

### 2. Create a database and user

Open a terminal (Linux) or **psql** console (Windows) and run:

```sql
CREATE DATABASE <database_name>;
CREATE USER <superuser_name> WITH PASSWORD '<your_password_here>';
GRANT ALL PRIVILEGES ON DATABASE <database_name> TO <superuser_name>;
\c <database_name>
GRANT ALL ON SCHEMA public TO <superuser_name>;
\q
```

Replace the placeholders (`<database_name>`, `<superuser_name>`, `<your_password_here>`) with values of your choice.

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit the newly created `.env` file and set the `DATABASE_URL` variable, e.g.:

```dotenv
DATABASE_URL=postgresql://<superuser_name>:<your_password_here>@localhost:5432/<database_name>
```

### 4. Set up a Python virtual environment

#### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### Windows

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 5. Install project dependencies

```bash
pip install -r requirements.txt
```

### 6. Run the application

```bash
fastapi dev app/main.py
```

The API will be available at `http://127.0.0.1:8000`.

## Verifying the setup

```bash
# Linux
which python
# Windows (PowerShell)
Get-Command python
```

Both commands should point to the Python interpreter inside the `.venv` directory.

## Contributing

Feel free to open issues or submit pull requests.