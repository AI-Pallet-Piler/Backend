# Backend
This repo contains the backend API.
It acts as the main data source and performs algorithmic calculations.

## Setup

### Create local Postgres database

#### Linux

`sudo apt update && sudo apt install -y postgresql postgresql-contrib`

```
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

```
CREATE DATABASE <database_name>;
CREATE USER <user_name> WITH PASSWORD '<your_password_here>';
GRANT ALL PRIVILEGES ON DATABASE <database_name> TO <user_name>;
\q`
```

### Run Project

**Enter virtual environment**

```
cd <project_root>
python -m venv
source .venv/bin/activate
```

**Install project packages**

`pip install -r requirements.txt`


**Enter app dir**

`cd app`


**Run app**

`fastapi dev main.py`

**Verify environment**

`which python`

- Should output *<project_dir>/.venv/\<something>/python*