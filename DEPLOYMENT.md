# PG Finder Deployment Checklist

## Required Environment Variables

Set these on your hosting platform before starting the app:

```bash
SECRET_KEY=replace-with-a-long-random-secret
DB_HOST=your-database-host
DB_USER=your-database-user
DB_PASSWORD=your-database-password
DB_NAME=pgfinder
FLASK_ENV=production
FLASK_DEBUG=0
MAX_CONTENT_LENGTH=8388608
CLOUDINARY_CLOUD_NAME=your-cloudinary-cloud-name
CLOUDINARY_API_KEY=your-cloudinary-api-key
CLOUDINARY_API_SECRET=your-cloudinary-api-secret
```

Generate a strong `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

## Local Development

For your laptop, create a `.env` file in the project root. This file is ignored by git, so it will not be pushed.

```bash
SECRET_KEY=dev-secret-change-me
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your-local-mysql-password
DB_NAME=pgfinder
FLASK_ENV=development
FLASK_DEBUG=1
MAX_CONTENT_LENGTH=8388608
CLOUDINARY_CLOUD_NAME=your-cloudinary-cloud-name
CLOUDINARY_API_KEY=your-cloudinary-api-key
CLOUDINARY_API_SECRET=your-cloudinary-api-secret
```

Then run:

```powershell
venv\Scripts\python.exe app.py
```

The app will create the `pgfinder` database and tables automatically if your local MySQL server is running and the user has permission.

If the Cloudinary variables are set, new listing images upload to Cloudinary. If they are missing, local development falls back to saving images in `static/images`.

## Production Start Command

Use this on Linux hosting platforms:

```bash
gunicorn app:app --bind 0.0.0.0:$PORT
```

For local Windows testing with your current database password:

```powershell
venv\Scripts\python.exe app.py
```

## Database Notes

The app automatically expands `users.password` to `VARCHAR(255)` when signup/login runs, so secure password hashes fit.

Before real launch, create your first admin directly in MySQL or promote a user manually. Public signup only allows `user` and `owner`.

## Security Changes Already Applied

- Passwords are hashed for new signups.
- Old plain-text passwords are upgraded to hashes on successful login.
- CSRF protection is enabled for POST requests.
- Listing deletion is POST-only.
- Image uploads are restricted to JPG, PNG, WEBP, and AVIF.
- Upload size is limited by `MAX_CONTENT_LENGTH`.
- Debug mode is off unless `FLASK_DEBUG=1`.
- Secrets and database credentials are read from environment variables.
