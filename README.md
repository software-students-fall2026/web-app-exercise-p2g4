# Web Application Exercise

A little exercise to build a web application following an agile development process. See the [instructions](instructions.md) for more detail.

## Product vision statement

Our NYU dining hall reviews app will allow students to review and critique NYU dining halls, and help other students know where to best spend their meal swipes and dining dollars.

## User stories

[User Stories (Issues)](https://github.com/orgs/software-students-fall2026/projects/56/views/2)

## Steps necessary to run the software

### Prerequisites

- Python 3 (version listed in Pipfile)
- pipenv
- Git
- A MongoDB database (e.g. MongoDB Atlas) and its connection string

### 1. Clone the repository

```
git clone https://github.com/software-students-fall2026/web-app-exercise-p2g4
cd web-app-exercise-p2g4
```

### 2. Install dependencies

```
pipenv install --dev
```

### 3. Configure environment variables

Create a `.env` file in the project root directory using `env.example`:

```bash
cp env.example .env
```

Open `.env` and configure the following variables:

```dotenv
MONGO_URI=your_mongodb_connection_string
MONGO_DB_NAME=nyu_dining
FLASK_SECRET_KEY=your_secret_key
```

To configure MongoDB Atlas:

1. Log in to MongoDB Atlas.
2. Create or select your database cluster.
3. Create a database user with appropriate permissions.
4. Under Network Access, allow your current IP address.
5. Copy the MongoDB connection string into the `.env` file.
6. Replace the placeholder credentials with your database username and password.

The `.env` file contains sensitive information and must not be committed to GitHub.

### 4. Load dining hall data (first run only)

Run the database seed script:

```bash
python3 -m pipenv run python -m scripts.seed_dining_halls
```

This initializes the dining halls collection in MongoDB.

Make sure the MongoDB connection is working before running this command.

### 5. Run the app

Start the Flask application:

```bash
python3 -m pipenv run python app.py
```

Open the application in your browser:

http://127.0.0.1:5000

## Task boards

[Task Board](https://github.com/orgs/software-students-fall2026/projects/56)
