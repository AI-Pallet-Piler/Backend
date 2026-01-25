# Backend
This repo contains the backend API.
It acts as the main data source and performs algorithmic calculations.

## Setup

### Create local Postgres database

#### Linux

##### Install packages

`sudo apt update && sudo apt install -y postgresql postgresql-contrib`

```
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

##### Create the DB
```
CREATE DATABASE <database_name>;
CREATE USER <superuser_name> WITH PASSWORD '<your_password_here>';
GRANT ALL PRIVILEGES ON DATABASE <database_name> TO <super_user_name>;

# Connect to your database
\c <database_name>

# Grant all privileges on the public schema to <super_user_name>
GRANT ALL ON SCHEMA public TO <super_user_name>;
\q`
```
##### Enter connection string

Copy the '.env.example' file to '.env' & fill in the DATABASE_URL using your credentials

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