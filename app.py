# =========================
# FULL MYSQL UPDATED app.py
# =========================

from flask import Flask, render_template, request, redirect, session, flash, jsonify, make_response, abort, url_for, send_from_directory
import mysql.connector
import requests
import os
import math
import secrets
import json
import hashlib
from urllib.parse import unquote, urlparse
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

try:
    from pywebpush import WebPushException, webpush
except ImportError:
    WebPushException = None
    webpush = None

try:
    import cloudinary
    import cloudinary.uploader
except ImportError:
    cloudinary = None


def load_env_file(path=".env"):
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and key not in os.environ:
                os.environ[key] = value


load_env_file()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 14
)

if os.environ.get("FLASK_ENV") == "production" and app.secret_key == "dev-only-change-me":
    raise RuntimeError("SECRET_KEY must be set in production")

production_db_password = (
    os.environ.get("DB_PASSWORD")
    or os.environ.get("MYSQLPASSWORD")
    or os.environ.get("MYSQL_ROOT_PASSWORD")
    or os.environ.get("MYSQL_PASSWORD")
)

if os.environ.get("FLASK_ENV") == "production" and not production_db_password:
    raise RuntimeError("DB_PASSWORD must be set in production")

UPLOAD_FOLDER = "static/images"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_CONTENT_LENGTH", 8 * 1024 * 1024))

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "avif"}
MAX_LISTING_IMAGES = int(os.environ.get("MAX_LISTING_IMAGES", "8"))
RENT_PERIODS = {"day", "week", "month"}
PRICE_MONTHLY_SQL = """
(
    CAST(price AS UNSIGNED) *
    CASE COALESCE(rent_period, 'month')
        WHEN 'day' THEN 30
        WHEN 'week' THEN 4
        ELSE 1
    END
)
"""

CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET")
CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL")
CLOUDINARY_ENABLED = bool(CLOUDINARY_URL) or all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET])
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "").replace("\\n", "\n").strip()
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:pgfinder@example.com")
WEB_PUSH_ENABLED = bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY and webpush)

if CLOUDINARY_ENABLED:
    if cloudinary is None:
        raise RuntimeError("Cloudinary variables are set, but the cloudinary package is not installed")

    if CLOUDINARY_URL:
        cloudinary.config(secure=True)
    else:
        cloudinary.config(
            cloud_name=CLOUDINARY_CLOUD_NAME,
            api_key=CLOUDINARY_API_KEY,
            api_secret=CLOUDINARY_API_SECRET,
            secure=True
        )

INDIA_MAP_CENTER = {
    "lat": 22.9734,
    "lng": 78.6569
}

LOCATION_FALLBACKS = [
    {"name": "Delhi, India", "lat": "28.6139", "lon": "77.2090"},
    {"name": "Mumbai, Maharashtra, India", "lat": "19.0760", "lon": "72.8777"},
    {"name": "Bengaluru, Karnataka, India", "lat": "12.9716", "lon": "77.5946"},
    {"name": "Hyderabad, Telangana, India", "lat": "17.3850", "lon": "78.4867"},
    {"name": "Ahmedabad, Gujarat, India", "lat": "23.0225", "lon": "72.5714"},
    {"name": "Srinagar, Jammu and Kashmir, India", "lat": "34.0837", "lon": "74.7973"},
    {"name": "Chandigarh, India", "lat": "30.7333", "lon": "76.7794"},
    {"name": "Pune, Maharashtra, India", "lat": "18.5204", "lon": "73.8567"},
    {"name": "Kolkata, West Bengal, India", "lat": "22.5726", "lon": "88.3639"},
    {"name": "Chennai, Tamil Nadu, India", "lat": "13.0827", "lon": "80.2707"},
    {"name": "Jaipur, Rajasthan, India", "lat": "26.9124", "lon": "75.7873"},
    {"name": "Lucknow, Uttar Pradesh, India", "lat": "26.8467", "lon": "80.9462"},
    {"name": "Indore, Madhya Pradesh, India", "lat": "22.7196", "lon": "75.8577"},
    {"name": "Bhopal, Madhya Pradesh, India", "lat": "23.2599", "lon": "77.4126"},
    {"name": "Noida, Uttar Pradesh, India", "lat": "28.5355", "lon": "77.3910"},
    {"name": "Gurugram, Haryana, India", "lat": "28.4595", "lon": "77.0266"},
    {"name": "Rohini, Delhi, India", "lat": "28.7383", "lon": "77.0822"},
    {"name": "Vastrapur, Ahmedabad, Gujarat, India", "lat": "23.0374", "lon": "72.5293"},
    {"name": "Ghatlodiya, Ahmedabad, Gujarat, India", "lat": "23.0677", "lon": "72.5443"},
    {"name": "Rajbagh, Srinagar, Jammu and Kashmir, India", "lat": "34.0666", "lon": "74.8194"},
    {"name": "Lal Chowk, Srinagar, Jammu and Kashmir, India", "lat": "34.0710", "lon": "74.8097"},
    {"name": "Hazratbal, Srinagar, Jammu and Kashmir, India", "lat": "34.1287", "lon": "74.8391"}
]


@app.template_filter("rent_period_label")
def rent_period_label(value):
    labels = {
        "day": "day",
        "week": "week",
        "month": "month"
    }

    return labels.get(value or "month", "month")


def clean_rent_period(value):
    value = (value or "month").strip().lower()

    if value not in RENT_PERIODS:
        return "month"

    return value


def render_app_error(title, message, status_code=400, action_label="Back home", action_href="/"):
    return render_template(
        "error.html",
        title=title,
        message=message,
        action_label=action_label,
        action_href=action_href
    ), status_code


def parse_positive_price(value):
    try:
        price = int(str(value).strip())
    except (TypeError, ValueError):
        return None

    if price <= 0:
        return None

    return str(price)


def parse_coordinate(value, minimum, maximum):
    try:
        coordinate = float(str(value).strip())
    except (TypeError, ValueError):
        return None

    if coordinate < minimum or coordinate > maximum:
        return None

    return str(coordinate)


def clean_listing_form(form, fallback_latitude=None, fallback_longitude=None):
    title = (form.get("title") or "").strip()
    price = parse_positive_price(form.get("price"))
    rent_period = clean_rent_period(form.get("rent_period"))
    room_type = (form.get("room_type") or "").strip()
    sharing_type = (form.get("sharing_type") or "").strip()
    amenities = ",".join(form.getlist("amenities"))
    location = (form.get("location") or "").strip()
    description = (form.get("description") or "").strip()
    latitude = parse_coordinate(form.get("latitude") or fallback_latitude, -90, 90)
    longitude = parse_coordinate(form.get("longitude") or fallback_longitude, -180, 180)

    if not title:
        return None, "Listing title is required."

    if not price:
        return None, "Rent amount must be a positive number."

    if not location:
        return None, "Location is required."

    if not latitude or not longitude:
        return None, "Please select a location suggestion or click the map so coordinates are saved."

    if not description:
        return None, "Description is required."

    return {
        "title": title,
        "price": price,
        "rent_period": rent_period,
        "room_type": room_type,
        "sharing_type": sharing_type,
        "amenities": amenities,
        "location": location,
        "description": description,
        "latitude": latitude,
        "longitude": longitude
    }, None


# =========================
# DATABASE CONNECTION
# =========================
def env_first(*names, default=""):
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def db_config(include_database=True):
    database_name = env_first("DB_NAME", "MYSQLDATABASE", "MYSQL_DATABASE", default="pgfinder")
    config = {
        "host": env_first("DB_HOST", "MYSQLHOST", "MYSQL_HOST", default="localhost"),
        "user": env_first("DB_USER", "MYSQLUSER", "MYSQL_USER", default="root"),
        "password": env_first(
            "DB_PASSWORD",
            "MYSQLPASSWORD",
            "MYSQL_ROOT_PASSWORD",
            "MYSQL_PASSWORD",
            default=""
        ),
    }

    if include_database:
        config["database"] = database_name

    return config, database_name


def validate_database_name(database_name):
    if not database_name or not all(char.isalnum() or char == "_" for char in database_name):
        raise RuntimeError("Database name may only contain letters, numbers, and underscores")


def create_index_if_missing(cursor, table_name, index_name, columns):
    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = %s
        AND INDEX_NAME = %s
    """, (table_name, index_name))

    if cursor.fetchone()["total"]:
        return

    column_sql = ", ".join(columns)
    cursor.execute(f"CREATE INDEX {index_name} ON {table_name} ({column_sql})")


def db():
    config, database_name = db_config()
    validate_database_name(database_name)

    try:
        conn = mysql.connector.connect(**config)
    except mysql.connector.Error as err:
        if err.errno != mysql.connector.errorcode.ER_BAD_DB_ERROR:
            raise

        server_config, _ = db_config(include_database=False)
        setup_conn = mysql.connector.connect(**server_config)
        setup_cursor = setup_conn.cursor()
        setup_cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database_name}`")
        setup_conn.commit()
        setup_conn.close()
        conn = mysql.connector.connect(**config)

    return conn


def ensure_database_schema():

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL,
            phone VARCHAR(30) NULL,
            role VARCHAR(30) NOT NULL DEFAULT 'user'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            price VARCHAR(50) NOT NULL,
            rent_period VARCHAR(20) NOT NULL DEFAULT 'month',
            room_type VARCHAR(30) NULL,
            sharing_type VARCHAR(30) NULL,
            amenities TEXT NULL,
            location TEXT NOT NULL,
            description TEXT NOT NULL,
            latitude VARCHAR(80) NULL,
            longitude VARCHAR(80) NULL,
            owner_id INT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS listing_images (
            id INT AUTO_INCREMENT PRIMARY KEY,
            listing_id INT NOT NULL,
            image TEXT NOT NULL
        )
    """)

    cursor.execute("""
        ALTER TABLE listing_images
        MODIFY image TEXT NOT NULL
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INT AUTO_INCREMENT PRIMARY KEY,
            listing_id INT NOT NULL,
            user_id INT NOT NULL,
            message TEXT NULL,
            phone VARCHAR(30) NULL,
            email VARCHAR(255) NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'pending'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contact_messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NULL,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL,
            subject VARCHAR(255) NOT NULL,
            message TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            endpoint TEXT NOT NULL,
            endpoint_hash CHAR(64) NOT NULL,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            user_agent TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uniq_push_endpoint_hash (endpoint_hash)
        )
    """)

    create_index_if_missing(cursor, "users", "idx_users_role", ["role"])
    create_index_if_missing(cursor, "listings", "idx_listings_owner", ["owner_id"])
    create_index_if_missing(cursor, "listings", "idx_listings_location", ["location(120)"])
    create_index_if_missing(cursor, "listing_images", "idx_listing_images_listing", ["listing_id"])
    create_index_if_missing(cursor, "requests", "idx_requests_listing", ["listing_id"])
    create_index_if_missing(cursor, "requests", "idx_requests_user", ["user_id"])
    create_index_if_missing(cursor, "requests", "idx_requests_status", ["status"])
    create_index_if_missing(cursor, "contact_messages", "idx_contact_messages_user", ["user_id"])
    create_index_if_missing(cursor, "push_subscriptions", "idx_push_subscriptions_user", ["user_id"])

    conn.commit()
    conn.close()


def csrf_token():
    token = session.get("_csrf_token")

    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token

    return token


def static_asset_version(filename):
    static_path = os.path.join(app.static_folder, filename.replace("/", os.sep))

    try:
        return str(int(os.path.getmtime(static_path)))
    except OSError:
        return "1"


@app.context_processor
def inject_csrf_token():
    return {
        "csrf_token": csrf_token,
        "image_src": image_src,
        "static_asset_version": static_asset_version
    }


@app.before_request
def protect_post_requests():
    if request.method != "POST":
        return

    expected = session.get("_csrf_token")
    submitted = request.form.get("_csrf_token") or request.headers.get("X-CSRFToken")

    if not expected or not submitted or not secrets.compare_digest(expected, submitted):
        abort(400, "Invalid CSRF token")


@app.after_request
def set_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@app.errorhandler(404)
def not_found(_error):
    return render_app_error(
        "Page not found",
        "The page you opened does not exist or may have moved.",
        404,
        "Back home",
        "/"
    )


@app.errorhandler(413)
def upload_too_large(_error):
    return render_app_error(
        "Upload too large",
        "Please upload smaller images and try again.",
        413,
        "Back",
        urlparse(request.referrer or "").path if is_safe_redirect_path(urlparse(request.referrer or "").path) else "/"
    )


@app.errorhandler(500)
def server_error(_error):
    return render_app_error(
        "Something went wrong",
        "Please try again. If this keeps happening, contact support.",
        500,
        "Back home",
        "/"
    )


def allowed_image(filename):
    if not filename or "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()
    return extension in ALLOWED_IMAGE_EXTENSIONS


def save_uploaded_image(file):
    if not file or not file.filename:
        return None

    if not allowed_image(file.filename):
        abort(400, "Only JPG, PNG, WEBP, and AVIF images are allowed")

    filename = secure_filename(file.filename)
    if not filename:
        abort(400, "Invalid image filename")

    name, extension = os.path.splitext(filename)

    if CLOUDINARY_ENABLED:
        upload = cloudinary.uploader.upload(
            file,
            folder="pgfinder/listings",
            public_id=f"{name[:60]}-{secrets.token_hex(8)}",
            resource_type="image",
            overwrite=False
        )
        return upload["secure_url"]

    if os.environ.get("FLASK_ENV") == "production":
        abort(
            500,
            "Cloudinary is not configured. Set CLOUDINARY_URL or the separate Cloudinary credentials."
        )

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    unique_filename = f"{name[:60]}-{secrets.token_hex(8)}{extension.lower()}"
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_filename))

    return unique_filename


def image_src(image):
    if not image:
        return url_for("static", filename="images/aesthetic-room-decor.jpg")

    if str(image).startswith(("http://", "https://")):
        return image

    return url_for("static", filename=f"images/{image}")


def cloudinary_public_id_from_url(image_url):
    parsed = urlparse(image_url)

    if not parsed.netloc.endswith("cloudinary.com") or "/upload/" not in parsed.path:
        return None

    upload_path = parsed.path.split("/upload/", 1)[1]
    path_parts = [part for part in upload_path.split("/") if part]

    while path_parts and not path_parts[0].startswith("v") and "/" in upload_path:
        if path_parts[0] == "pgfinder":
            break
        path_parts.pop(0)

    if path_parts and path_parts[0].startswith("v") and path_parts[0][1:].isdigit():
        path_parts.pop(0)

    if not path_parts:
        return None

    public_path = unquote("/".join(path_parts))
    public_id, _ = os.path.splitext(public_path)
    return public_id or None


def delete_stored_image(image):
    if not image:
        return

    image = str(image)

    if image.startswith(("http://", "https://")):
        public_id = cloudinary_public_id_from_url(image)

        if CLOUDINARY_ENABLED and public_id:
            cloudinary.uploader.destroy(public_id, resource_type="image")

        return

    image_path = os.path.abspath(os.path.join(app.config["UPLOAD_FOLDER"], image))
    upload_root = os.path.abspath(app.config["UPLOAD_FOLDER"])

    if os.path.commonpath([upload_root, image_path]) == upload_root and os.path.exists(image_path):
        os.remove(image_path)


def delete_listing_images_from_storage(cursor, listing_id):
    cursor.execute("""
        SELECT image
        FROM listing_images
        WHERE listing_id=%s
    """, (listing_id,))

    for image in cursor.fetchall():
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM listing_images
            WHERE image=%s
            AND listing_id<>%s
        """, (image["image"], listing_id))

        used_elsewhere = cursor.fetchone()["total"]

        if not used_elsewhere:
            delete_stored_image(image["image"])


def is_owner_or_admin():
    return session.get("role") in ("owner", "admin")


def is_admin():
    return session.get("role") == "admin"


def is_safe_redirect_path(path):
    return bool(path) and path.startswith("/") and not path.startswith("//")


def wants_json_response():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.accept_mimetypes.best == "application/json"


def endpoint_hash(endpoint):
    return hashlib.sha256((endpoint or "").encode("utf-8")).hexdigest()


def push_payload(title, message, url="/", notification_type="info"):
    return {
        "title": title,
        "message": message,
        "url": url,
        "type": notification_type,
        "icon": url_for("static", filename="images/aesthetic-room-decor.jpg", _external=True),
        "badge": url_for("static", filename="images/aesthetic-room-decor.jpg", _external=True)
    }


def delete_push_subscription(cursor, endpoint):
    cursor.execute("""
        DELETE FROM push_subscriptions
        WHERE endpoint_hash=%s
    """, (endpoint_hash(endpoint),))


def send_web_push_to_user(user_id, payload):
    if not WEB_PUSH_ENABLED:
        return {"sent": 0, "failed": 0, "removed": 0, "enabled": False}

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT endpoint, p256dh, auth
        FROM push_subscriptions
        WHERE user_id=%s
    """, (user_id,))

    subscriptions = cursor.fetchall()
    stats = {
        "sent": 0,
        "failed": 0,
        "removed": 0,
        "enabled": True,
        "subscriptions": len(subscriptions)
    }

    for subscription in subscriptions:
        push_subscription = {
            "endpoint": subscription["endpoint"],
            "keys": {
                "p256dh": subscription["p256dh"],
                "auth": subscription["auth"]
            }
        }

        try:
            webpush(
                subscription_info=push_subscription,
                data=json.dumps(payload),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_SUBJECT}
            )
            stats["sent"] += 1
        except Exception as err:
            status_code = getattr(getattr(err, "response", None), "status_code", None)
            if WebPushException and isinstance(err, WebPushException) and status_code in (404, 410):
                delete_push_subscription(cursor, subscription["endpoint"])
                stats["removed"] += 1
            else:
                stats["failed"] += 1
                app.logger.info("Web push failed for user %s: %s", user_id, err.__class__.__name__)

    conn.commit()
    conn.close()
    return stats


def calculate_distance_km(lat1, lon1, lat2, lon2):
    earth_radius_km = 6371

    lat1 = math.radians(float(lat1))
    lon1 = math.radians(float(lon1))
    lat2 = math.radians(float(lat2))
    lon2 = math.radians(float(lon2))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )

    return earth_radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# Health check route used by Railway/deploy platforms to confirm the app is alive.
@app.route("/healthz")
def healthz():
    status = {
        "ok": True,
        "database": "unknown",
        "cloudinary": "configured" if CLOUDINARY_ENABLED else "missing",
        "environment": os.environ.get("FLASK_ENV", "development")
    }

    try:
        conn = db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT 1 AS ok")
        cursor.fetchone()
        conn.close()
        status["database"] = "ok"
    except Exception as err:
        status["ok"] = False
        status["database"] = "error"
        status["database_error"] = err.__class__.__name__

    http_status = 200 if status["ok"] else 503
    return jsonify(status), http_status


def ensure_contact_messages_user_id():

    ensure_database_schema()

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contact_messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NULL,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL,
            subject VARCHAR(255) NOT NULL,
            message TEXT NOT NULL
        )
    """)

    conn.commit()

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'contact_messages'
        AND COLUMN_NAME = 'user_id'
    """)

    exists = cursor.fetchone()["total"]

    if not exists:
        cursor.execute("""
            ALTER TABLE contact_messages
            ADD COLUMN user_id INT NULL
        """)
        conn.commit()

    conn.close()


def ensure_listing_filter_columns():

    ensure_database_schema()

    conn = db()
    cursor = conn.cursor(dictionary=True)

    required_columns = {
        "rent_period": "VARCHAR(20) NOT NULL DEFAULT 'month'",
        "room_type": "VARCHAR(30) NULL",
        "sharing_type": "VARCHAR(30) NULL",
        "amenities": "TEXT NULL"
    }

    cursor.execute("""
        SELECT COLUMN_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'listings'
    """)

    existing_columns = {
        row["COLUMN_NAME"]
        for row in cursor.fetchall()
    }

    for column, definition in required_columns.items():

        if column not in existing_columns:
            try:
                cursor.execute(f"""
                    ALTER TABLE listings
                    ADD COLUMN {column} {definition}
                """)
            except mysql.connector.Error as err:
                if err.errno != 1060:
                    conn.close()
                    raise

    conn.commit()
    conn.close()


def ensure_push_subscription_columns():

    ensure_database_schema()

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT COLUMN_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'push_subscriptions'
    """)

    existing_columns = {
        row["COLUMN_NAME"]
        for row in cursor.fetchall()
    }

    if "user_agent" not in existing_columns:
        cursor.execute("""
            ALTER TABLE push_subscriptions
            ADD COLUMN user_agent TEXT NULL
        """)

    conn.commit()
    conn.close()


def ensure_user_auth_columns():

    ensure_database_schema()

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT CHARACTER_MAXIMUM_LENGTH AS max_length
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'users'
        AND COLUMN_NAME = 'password'
    """)

    password_column = cursor.fetchone()

    if password_column and (password_column["max_length"] or 0) < 255:
        cursor.execute("""
            ALTER TABLE users
            MODIFY password VARCHAR(255) NOT NULL
        """)

    conn.commit()
    conn.close()


def initialize_notification_state(user_id, role):

    conn = db()
    cursor = conn.cursor(dictionary=True)

    if role in ("owner", "admin"):

        if role == "admin":
            cursor.execute("""
                SELECT COALESCE(MAX(id), 0) AS latest_id
                FROM requests
            """)
        else:
            cursor.execute("""
                SELECT COALESCE(MAX(requests.id), 0) AS latest_id
                FROM requests
                JOIN listings ON requests.listing_id = listings.id
                WHERE listings.owner_id=%s
            """, (user_id,))

        session["owner_seen_request_id"] = cursor.fetchone()["latest_id"] or 0

    cursor.execute("""
        SELECT id, status
        FROM requests
        WHERE user_id=%s
    """, (user_id,))

    session["user_seen_request_statuses"] = {
        str(req["id"]): req["status"]
        for req in cursor.fetchall()
    }

    conn.close()


# =========================
# GET COORDINATES
# =========================
def get_coordinates(place):

    url = "https://nominatim.openstreetmap.org/search"

    headers = {
        "User-Agent": "PGFinder"
    }

    response = requests.get(
        url,
        params={"q": place, "format": "json"},
        headers=headers,
        timeout=6
    )

    data = response.json()

    if data:

        latitude = data[0]["lat"]
        longitude = data[0]["lon"]

        return latitude, longitude

    return None, None


def fallback_location_results(query):
    query = (query or "").lower()
    matches = [
        place for place in LOCATION_FALLBACKS
        if query in place["name"].lower()
    ]

    return [
        {
            "name": place["name"],
            "lat": place["lat"],
            "lon": place["lon"],
            "type": "fallback"
        }
        for place in (matches or LOCATION_FALLBACKS[:5])
    ]


# Location autocomplete API used by listing forms and search inputs.
@app.route("/api/location-search")
def location_search():

    query = request.args.get("q", "").strip()

    if len(query) < 2:
        return jsonify([])

    params = {
        "format": "jsonv2",
        "q": query,
        "limit": 10,
        "addressdetails": 1,
        "countrycodes": "in"
    }

    headers = {
        "User-Agent": "PGFinder/1.0 (Railway app; owner location search)",
        "Accept-Language": "en-IN,en;q=0.9"
    }

    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers=headers,
            timeout=2
        )
        response.raise_for_status()
        places = response.json()
    except requests.RequestException:
        return jsonify(fallback_location_results(query))

    results = []

    for place in places:

        display_name = place.get("display_name", "")

        results.append({
            "name": display_name,
            "lat": place.get("lat"),
            "lon": place.get("lon"),
            "type": place.get("type", "place")
        })

    return jsonify(results or fallback_location_results(query))


# Reverse geocoding API that turns map coordinates into a readable place name.
@app.route("/api/reverse-location")
def reverse_location():

    lat = request.args.get("lat")
    lon = request.args.get("lon")

    if not lat or not lon:
        return jsonify({"error": "Latitude and longitude are required"}), 400

    params = {
        "format": "jsonv2",
        "lat": lat,
        "lon": lon,
        "zoom": 18,
        "addressdetails": 1
    }

    headers = {
        "User-Agent": "PGFinder/1.0 (Railway app; owner reverse geocoding)",
        "Accept-Language": "en-IN,en;q=0.9"
    }

    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params=params,
            headers=headers,
            timeout=6
        )
        response.raise_for_status()
        place = response.json()
    except requests.RequestException:
        return jsonify({"error": "Unable to read location"}), 502

    return jsonify({
        "name": place.get("display_name", "Custom Location"),
        "lat": lat,
        "lon": lon
    })


# =========================
# HOME
# =========================
# Main browsing route: renders Home at "/" and Advanced Find at "/find" with shared filtering logic.
@app.route("/")
@app.route("/find")
def home():

    ensure_listing_filter_columns()

    search = request.args.get("search", "")
    category_filter = request.args.get("category", "")
    room_type = request.args.get("room_type", "")
    sharing = request.args.get("sharing", "")
    min_price = request.args.get("min_price", "")
    max_price = request.args.get("max_price", "")
    sort = request.args.get("sort", "newest")
    amenities = request.args.getlist("amenity")
    nearby = request.args.get("nearby") == "1"
    user_lat = request.args.get("lat")
    user_lng = request.args.get("lng")
    radius = request.args.get("radius", "5")

    try:
        radius_km = float(radius)
    except ValueError:
        radius_km = 5

    nearby_active = nearby and user_lat and user_lng

    conn = db()
    cursor = conn.cursor(dictionary=True)

    where_clauses = []
    params = []

    if search:
        where_clauses.append("""
            (
                location LIKE %s
                OR title LIKE %s
                OR description LIKE %s
            )
        """)
        search_value = '%' + search + '%'
        params.extend([search_value, search_value, search_value])

    if category_filter == "budget":
        where_clauses.append(f"{PRICE_MONTHLY_SQL} <= %s")
        params.append(7000)
    elif category_filter == "premium":
        where_clauses.append(f"{PRICE_MONTHLY_SQL} BETWEEN %s AND %s")
        params.extend([10000, 20000])
    elif category_filter == "luxury":
        where_clauses.append(f"{PRICE_MONTHLY_SQL} > %s")
        params.append(20000)

    room_keywords = {
        "1bhk": ["1bhk", "1 bhk", "1-bhk"],
        "2bhk": ["2bhk", "2 bhk", "2-bhk"],
        "3bhk": ["3bhk", "3 bhk", "3-bhk"],
        "room": ["room", "single room"],
        "studio": ["studio"],
        "pg": ["pg", "paying guest"]
    }

    if room_type in room_keywords:
        keyword_clauses = []

        for keyword in room_keywords[room_type]:
            keyword_clauses.append("""
                (
                    room_type=%s
                    OR LOWER(title) LIKE %s
                    OR LOWER(description) LIKE %s
                )
            """)
            params.extend([room_type, '%' + keyword + '%', '%' + keyword + '%'])

        where_clauses.append("(" + " OR ".join(keyword_clauses) + ")")

    sharing_keywords = {
        "single": ["single", "private"],
        "double": ["double", "2 sharing", "two sharing"],
        "triple": ["triple", "3 sharing", "three sharing"],
        "shared": ["shared", "sharing"]
    }

    if sharing in sharing_keywords:
        keyword_clauses = []

        for keyword in sharing_keywords[sharing]:
            keyword_clauses.append("""
                (
                    sharing_type=%s
                    OR LOWER(title) LIKE %s
                    OR LOWER(description) LIKE %s
                )
            """)
            params.extend([sharing, '%' + keyword + '%', '%' + keyword + '%'])

        where_clauses.append("(" + " OR ".join(keyword_clauses) + ")")

    amenity_keywords = {
        "wifi": "wifi",
        "food": "food",
        "parking": "parking",
        "ac": "ac",
        "laundry": "laundry",
        "attached_bath": "attached"
    }

    for amenity in amenities:
        keyword = amenity_keywords.get(amenity)

        if keyword:
            where_clauses.append("""
                (
                    FIND_IN_SET(%s, amenities)
                    OR LOWER(title) LIKE %s
                    OR LOWER(description) LIKE %s
                )
            """)
            params.extend([amenity, '%' + keyword + '%', '%' + keyword + '%'])

    if min_price:
        where_clauses.append(f"{PRICE_MONTHLY_SQL} >= %s")
        params.append(min_price)

    if max_price:
        where_clauses.append(f"{PRICE_MONTHLY_SQL} <= %s")
        params.append(max_price)

    order_by = "id DESC"

    if sort == "price_low":
        order_by = f"{PRICE_MONTHLY_SQL} ASC"
    elif sort == "price_high":
        order_by = f"{PRICE_MONTHLY_SQL} DESC"

    query = "SELECT * FROM listings"

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    query += f" ORDER BY {order_by}"

    cursor.execute(query, tuple(params))

    listings = cursor.fetchall()

    data = []

    for listing in listings:

        distance_km = None

        if nearby_active:
            try:
                distance_km = calculate_distance_km(
                    user_lat,
                    user_lng,
                    listing["latitude"],
                    listing["longitude"]
                )
            except (TypeError, ValueError):
                continue

            if distance_km > radius_km:
                continue

        cursor.execute("""
            SELECT * FROM listing_images
            WHERE listing_id=%s
        """, (listing["id"],))

        images = cursor.fetchall()

        cursor.execute("""
            SELECT phone
            FROM users
            WHERE id=%s
        """, (listing["owner_id"],))

        owner = cursor.fetchone()

        request_status = None

        if "user_id" in session:

            cursor.execute("""
                SELECT status
                FROM requests
                WHERE listing_id=%s
                AND user_id=%s
            """, (
                listing["id"],
                session["user_id"]
            ))

            existing = cursor.fetchone()

            if existing:
                request_status = existing["status"]

        data.append({

            "listing": listing,
            "images": images,
            "phone": owner["phone"] if owner else "",
            "request_status": request_status,
            "distance_km": round(distance_km, 1) if distance_km is not None else None

        })

    if nearby_active:
        data.sort(key=lambda item: item["distance_km"])

    user = None

    if "user_id" in session:

        cursor.execute("""
            SELECT * FROM users
            WHERE id=%s
        """, (session["user_id"],))

        user = cursor.fetchone()

    conn.close()

    filters_active = bool(
        search or category_filter or room_type or sharing or min_price or max_price or amenities or sort != "newest"
    )

    is_find_page = request.path == "/find"
    find_batch_size = 3
    home_batch_size = 4
    try:
        listing_offset = max(0, int(request.args.get("offset", "0")))
    except ValueError:
        listing_offset = 0

    if is_find_page:
        limited_data = data[listing_offset:listing_offset + find_batch_size]
    elif request.headers.get("X-Requested-With") == "XMLHttpRequest":
        limited_data = data[listing_offset:listing_offset + home_batch_size]
    else:
        limited_data = data[:home_batch_size]

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        response = make_response(render_template(
            "listings_partial.html",
            data=limited_data
        ))
        response.headers["X-Total-Count"] = str(len(data))
        response.headers["X-Next-Offset"] = str(listing_offset + len(limited_data))
        return response

    return render_template(

        "find.html" if is_find_page else "home.html",

        data=limited_data,
        total=len(data),
        nearby_active=nearby_active,
        nearby_radius=radius_km,
        user_lat=user_lat,
        user_lng=user_lng,
        search=search,
        category_filter=category_filter,
        room_type=room_type,
        sharing=sharing,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
        amenities=amenities,
        filters_active=filters_active,
        find_batch_size=find_batch_size,
        home_batch_size=home_batch_size,
        rendered_count=len(limited_data),

        user=user,

        uid=session.get("user_id")

    )


# =========================
# SIGNUP
# =========================
# Signup route: creates a user/owner account and starts a logged-in session.
@app.route("/signup", methods=["GET", "POST"])
def signup():

    ensure_user_auth_columns()

    if request.method == "POST":

        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        phone = request.form["phone"].strip()
        role = request.form["role"]

        if not name or not email or not phone or not password:
            return render_template("signup.html", error="All fields are required."), 400

        if "@" not in email or "." not in email:
            return render_template("signup.html", error="Enter a valid email address."), 400

        if len(password) < 8:
            return render_template("signup.html", error="Password must be at least 8 characters."), 400

        if role not in ("user", "owner"):
            role = "user"

        conn = db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT id
            FROM users
            WHERE email=%s
        """, (email,))

        if cursor.fetchone():
            conn.close()
            return render_template("signup.html", error="Email already exists"), 409

        cursor.execute("""
            INSERT INTO users(name,email,password,phone,role)
            VALUES(%s,%s,%s,%s,%s)
        """, (name, email, generate_password_hash(password), phone, role))

        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("signup.html")


# =========================
# LOGIN
# =========================
# Login route: validates credentials, stores session data, and initializes notifications.
@app.route('/login', methods=['GET', 'POST'])
def login():

    ensure_user_auth_columns()

    if "user_id" in session:
        next_url = request.args.get("next") or "/"

        if not is_safe_redirect_path(next_url):
            next_url = "/"

        return redirect(next_url)

    error = None
    next_url = request.args.get("next") or request.form.get("next") or "/"

    if request.method == 'POST':

        email = request.form['email'].strip().lower()
        password = request.form['password'].strip()

        conn = db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT * FROM users
            WHERE email=%s
        """, (email,))

        user = cursor.fetchone()

        password_ok = False

        if user:
            stored_password = user.get("password") or ""

            try:
                password_ok = check_password_hash(stored_password, password)
            except ValueError:
                password_ok = False

            if not password_ok and stored_password == password:
                password_ok = True
                cursor.execute("""
                    UPDATE users
                    SET password=%s
                    WHERE id=%s
                """, (generate_password_hash(password), user["id"]))
                conn.commit()

        conn.close()

        if user and password_ok:

            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['name']
            session['role'] = user['role']
            initialize_notification_state(user["id"], user["role"])

            if not is_safe_redirect_path(next_url):
                next_url = "/"

            return redirect(next_url)

        else:

            error = "❌ Invalid Email or Password"

    return render_template(
        'login.html',
        error=error,
        next_url=next_url
    )


# =========================
# LOGOUT
# =========================
# Logout route: clears the current session and returns the user to the home page.
@app.route('/logout')
def logout():

    session.clear()

    return redirect('/')


# =========================
# ADD LISTING
# =========================
# =========================
# ADD LISTING
# =========================
# Add listing route: owners/admins create a new property with filters, location, and uploaded images.
@app.route("/add", methods=["GET", "POST"])
def add_listing():

    ensure_listing_filter_columns()

    if "user_id" not in session:
        return redirect("/login")

    conn = db()
    cursor = conn.cursor(dictionary=True)

    # GET USER
    cursor.execute("""
        SELECT * FROM users
        WHERE id=%s
    """, (session["user_id"],))

    user = cursor.fetchone()

    # IMPORTANT FIX
    if not user:
        conn.close()
        return render_app_error("Account not found", "Please log in again to continue.", 404, "Login", "/login")

    # OWNER CHECK
    if user["role"] not in ("owner", "admin"):

        conn.close()

        return render_app_error(
            "Owner access required",
            "Only owner accounts can publish PG listings.",
            403,
            "Go back home",
            "/"
        )

    # POST
    if request.method == "POST":

        listing_form, form_error = clean_listing_form(request.form)
        files = [
            file for file in request.files.getlist("images")
            if file and file.filename
        ]

        if form_error:
            conn.close()
            return render_app_error("Listing needs one fix", form_error, 400, "Back to Add Listing", "/add")

        if not files:
            conn.close()
            return render_app_error("Photos required", "Please upload at least one clear PG image.", 400, "Back to Add Listing", "/add")

        if len(files) > MAX_LISTING_IMAGES:
            conn.close()
            return render_app_error(
                "Too many photos",
                f"Please upload up to {MAX_LISTING_IMAGES} images per listing.",
                400,
                "Back to Add Listing",
                "/add"
            )

        saved_images = []

        try:
            cursor.execute("""
                INSERT INTO listings
                (
                    title, price, rent_period, room_type, sharing_type, amenities,
                    location, description, latitude, longitude, owner_id
                )

                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                listing_form["title"],
                listing_form["price"],
                listing_form["rent_period"],
                listing_form["room_type"],
                listing_form["sharing_type"],
                listing_form["amenities"],
                listing_form["location"],
                listing_form["description"],
                listing_form["latitude"],
                listing_form["longitude"],
                session["user_id"]
            ))

            listing_id = cursor.lastrowid

            for file in files:
                filename = save_uploaded_image(file)

                if filename:
                    saved_images.append(filename)
                    cursor.execute("""
                        INSERT INTO listing_images
                        (listing_id, image)

                        VALUES (%s,%s)
                    """, (listing_id, filename))

            conn.commit()
        except Exception:
            conn.rollback()

            for image in saved_images:
                delete_stored_image(image)

            conn.close()
            raise

        conn.close()

        return redirect("/")

    conn.close()

    return render_template("add_listing.html")

# =========================
# CATEGORY FILTER
# =========================
# Category route: shows listings filtered by a named category such as budget, premium, or luxury.
@app.route("/category/<name>")
def category(name):

    ensure_listing_filter_columns()

    nearby = request.args.get("nearby") == "1"
    user_lat = request.args.get("lat")
    user_lng = request.args.get("lng")
    radius = request.args.get("radius", "5")

    try:
        radius_km = float(radius)
    except ValueError:
        radius_km = 5

    nearby_active = nearby and user_lat and user_lng

    conn = db()
    cursor = conn.cursor(dictionary=True)

    if name == "luxury":

        cursor.execute(f"""
            SELECT * FROM listings
            WHERE {PRICE_MONTHLY_SQL} > 20000
            ORDER BY id DESC
        """)

    elif name == "budget":

        cursor.execute(f"""
            SELECT * FROM listings
            WHERE {PRICE_MONTHLY_SQL} <= 7000
            ORDER BY id DESC
        """)

    elif name == "premium":

        cursor.execute(f"""
            SELECT * FROM listings
            WHERE {PRICE_MONTHLY_SQL}
            BETWEEN 10000 AND 20000
            ORDER BY id DESC
        """)

    else:

        cursor.execute("""
            SELECT * FROM listings
            ORDER BY id DESC
        """)

    listings = cursor.fetchall()

    data = []

    for listing in listings:

        distance_km = None

        if nearby_active:
            try:
                distance_km = calculate_distance_km(
                    user_lat,
                    user_lng,
                    listing["latitude"],
                    listing["longitude"]
                )
            except (TypeError, ValueError):
                continue

            if distance_km > radius_km:
                continue

        cursor.execute("""
            SELECT * FROM listing_images
            WHERE listing_id=%s
        """, (listing["id"],))

        images = cursor.fetchall()

        cursor.execute("""
            SELECT phone FROM users
            WHERE id=%s
        """, (listing["owner_id"],))

        owner = cursor.fetchone()

        request_status = None

        if "user_id" in session:

            cursor.execute("""
                SELECT status
                FROM requests
                WHERE listing_id=%s
                AND user_id=%s
            """, (
                listing["id"],
                session["user_id"]
            ))

            existing = cursor.fetchone()

            if existing:
                request_status = existing["status"]

        data.append({

            "listing": listing,
            "images": images,
            "phone": owner["phone"] if owner else "",
            "request_status": request_status,
            "distance_km": round(distance_km, 1) if distance_km is not None else None

        })

    if nearby_active:
        data.sort(key=lambda item: item["distance_km"])

    conn.close()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return render_template(
            "listings_partial.html",
            data=data
        )

    return render_template(
        "find.html",
        data=data,
        total=len(data),
        nearby_active=nearby_active,
        nearby_radius=radius_km,
        user_lat=user_lat,
        user_lng=user_lng,
        search="",
        category_filter=name if name in ("budget", "luxury", "premium") else "",
        room_type="",
        sharing="",
        min_price="",
        max_price="",
        sort="newest",
        amenities=[],
        filters_active=False,
        uid=session.get("user_id")
    )


# =========================
# ALL LISTINGS
# =========================
# AJAX route for Home "View More": returns the full listing-card partial without reloading the page.
@app.route("/all-listings")
def all_listings():

    ensure_listing_filter_columns()

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM listings
        ORDER BY id DESC
    """)

    listings = cursor.fetchall()

    data = []

    for listing in listings:

        cursor.execute("""
            SELECT * FROM listing_images
            WHERE listing_id=%s
        """, (listing["id"],))

        images = cursor.fetchall()

        cursor.execute("""
            SELECT phone
            FROM users
            WHERE id=%s
        """, (listing["owner_id"],))

        owner = cursor.fetchone()

        data.append({

            "listing": listing,
            "images": images,
            "phone": owner["phone"] if owner else "",
            "request_status": None

        })

    conn.close()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return render_template(
            "listings_partial.html",
            data=data
        )

    return render_template(
        "find.html",
        data=data,
        total=len(data),
        nearby_active=False,
        nearby_radius=5,
        user_lat=None,
        user_lng=None,
        search="",
        category_filter="",
        room_type="",
        sharing="",
        min_price="",
        max_price="",
        sort="newest",
        amenities=[],
        filters_active=False,
        uid=session.get("user_id")
    )


# =========================
# LISTING DETAIL
# =========================
# =========================
# LISTING DETAIL
# =========================
# Listing detail route: shows one listing, its images, owner phone, map, and request state.
@app.route("/listing/<int:id>")
def listing_detail(id):

    ensure_listing_filter_columns()

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM listings
        WHERE id=%s
    """, (id,))

    listing = cursor.fetchone()

    # IMPORTANT FIX
    if not listing:
        conn.close()
        return render_app_error("Listing not found", "This listing is no longer available.", 404, "Browse listings", "/find")

    cursor.execute("""
        SELECT * FROM listing_images
        WHERE listing_id=%s
    """, (id,))

    images = cursor.fetchall()

    cursor.execute("""
        SELECT * FROM users
        WHERE id=%s
    """, (listing["owner_id"],))

    owner = cursor.fetchone()

    request_status = None

    if "user_id" in session:
        cursor.execute("""
            SELECT status
            FROM requests
            WHERE listing_id=%s
            AND user_id=%s
        """, (id, session["user_id"]))

        existing_request = cursor.fetchone()

        if existing_request:
            request_status = existing_request["status"]

    conn.close()

    return render_template(

        "listing_detail.html",

        listing=listing,
        images=images,
        owner=owner,
        request_status=request_status,
        request_notice=request.args.get("request"),

        uid=session.get("user_id")

    )


# =========================
# PROFILE PAGE
# =========================
# Profile route: shows the signed-in user's account details and activity snapshot.
@app.route("/profile")
def profile():

    # LOGIN CHECK
    if "user_id" not in session:
        return redirect("/login")

    conn = db()
    cursor = conn.cursor(dictionary=True)

    # USER
    cursor.execute("""
        SELECT * FROM users
        WHERE id=%s
    """, (session["user_id"],))

    user = cursor.fetchone()

    # SAFETY FIX
    if not user:
        conn.close()
        session.clear()
        return redirect("/login")

    # TOTAL LISTINGS
    cursor.execute("""
        SELECT COUNT(*) as total
        FROM listings
        WHERE owner_id=%s
    """, (session["user_id"],))

    total_listings = cursor.fetchone()["total"]

    conn.close()

    return render_template(

        "profile.html",

        user=user,
        total_listings=total_listings

    )

# Owner listings route: lets owners/admins review and manage their own posted properties.
@app.route("/my-listings")
def my_listings():

    if "user_id" not in session:
        return redirect("/login")

    if not is_owner_or_admin():
        return redirect("/")

    ensure_listing_filter_columns()

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM listings
        WHERE owner_id=%s
        ORDER BY id DESC
    """, (session["user_id"],))

    listings = cursor.fetchall()

    data = []

    for listing in listings:

        cursor.execute("""
            SELECT * FROM listing_images
            WHERE listing_id=%s
        """, (listing["id"],))

        images = cursor.fetchall()

        data.append({
            "listing": listing,
            "images": images
        })

    conn.close()

    return render_template(
        "my_listings.html",
        data=data
    )


# contacts

# Contact route: saves support/contact messages and links them to the user when logged in.
@app.route("/contact", methods=["GET", "POST"])
def contact():

    ensure_contact_messages_user_id()

    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":

        name = request.form["name"].strip()
        email = request.form["email"].strip()
        subject = request.form["subject"]
        message = request.form["message"].strip()

        conn = db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT id
            FROM contact_messages
            WHERE user_id=%s
            LIMIT 1
        """, (session["user_id"],))

        existing_message = cursor.fetchone()

        if existing_message:
            conn.close()
            return redirect("/contact?status=already-sent")

        cursor.execute("""
            INSERT INTO contact_messages
            (user_id, name, email, subject, message)

            VALUES (%s,%s,%s,%s,%s)
        """, (session["user_id"], name, email, subject, message))

        conn.commit()
        conn.close()

        return redirect("/contact?status=sent")

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM users
        WHERE id=%s
    """, (session["user_id"],))

    user = cursor.fetchone()

    cursor.execute("""
        SELECT *
        FROM contact_messages
        WHERE user_id=%s
        LIMIT 1
    """, (session["user_id"],))

    existing_message = cursor.fetchone()

    conn.close()

    return render_template(
        "contact.html",
        user=user,
        existing_message=existing_message,
        status=request.args.get("status")
    )




# =========================
# REQUESTS PAGE
# =========================
# Owner request inbox: shows booking/contact requests received for the owner's listings.
@app.route("/requests")
def requests_page():

    # LOGIN CHECK
    if "user_id" not in session:
        return redirect("/login")

    if not is_owner_or_admin():
        return redirect("/")

    conn = db()
    cursor = conn.cursor(dictionary=True)

    # FETCH REQUESTS
    request_query = """

        SELECT

        requests.*,

        users.name AS user_name,

        listings.title,

        (
            SELECT image
            FROM listing_images
            WHERE listing_images.listing_id = listings.id
            LIMIT 1
        ) AS image

        FROM requests

        JOIN users
        ON requests.user_id = users.id

        JOIN listings
        ON requests.listing_id = listings.id

    """

    params = ()

    if not is_admin():
        request_query += """
        WHERE listings.owner_id = %s
        """
        params = (session["user_id"],)

    request_query += """
        ORDER BY requests.id DESC

    """

    cursor.execute(request_query, params)

    requests_data = cursor.fetchall()

    conn.close()

    return render_template(
        "requests.html",
        requests=requests_data
    )


# User request tracker: shows requests the current user has sent to listing owners.
@app.route("/my-requests")
def my_requests():

    if "user_id" not in session:
        return redirect("/login")

    ensure_listing_filter_columns()

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            requests.*,
            listings.title,
            listings.location,
            listings.price,
            listings.rent_period,
            listings.latitude,
            listings.longitude,
            users.name AS owner_name,
            users.phone AS owner_phone,
            (
                SELECT image
                FROM listing_images
                WHERE listing_images.listing_id = listings.id
                LIMIT 1
            ) AS image
        FROM requests
        JOIN listings ON requests.listing_id = listings.id
        LEFT JOIN users ON listings.owner_id = users.id
        WHERE requests.user_id=%s
        ORDER BY requests.id DESC
    """, (session["user_id"],))

    sent_requests = cursor.fetchall()
    conn.close()

    return render_template(
        "my_requests.html",
        requests=sent_requests
    )


# Accept request action: owner/admin marks one listing request as accepted.
@app.route("/accept-request/<int:id>", methods=["POST"])
def accept_request(id):

    if "user_id" not in session:
        return redirect("/login")

    if not is_owner_or_admin():
        return redirect("/")

    conn = db()
    cursor = conn.cursor(dictionary=True)

    if is_admin():
        cursor.execute("""
            UPDATE requests
            SET status='accepted'
            WHERE id=%s
        """, (id,))
    else:
        cursor.execute("""
            UPDATE requests
            JOIN listings ON requests.listing_id = listings.id
            SET requests.status='accepted'
            WHERE requests.id=%s
            AND listings.owner_id=%s
        """, (id, session["user_id"]))

    updated = cursor.rowcount

    push_target = None
    if updated:
        cursor.execute("""
            SELECT requests.user_id, listings.title AS listing_title
            FROM requests
            JOIN listings ON requests.listing_id = listings.id
            WHERE requests.id=%s
        """, (id,))
        push_target = cursor.fetchone()

    conn.commit()
    conn.close()

    if push_target:
        send_web_push_to_user(
            push_target["user_id"],
            push_payload(
                "Request accepted",
                f"Your request for {push_target['listing_title']} was accepted.",
                "/my-requests",
                "request_accepted"
            )
        )

    if not updated:
        if wants_json_response():
            return jsonify({"error": "Request not found or not allowed"}), 404

        return redirect("/requests")

    if wants_json_response():
        return jsonify({"status": "accepted"})

    return redirect("/requests")


# Reject request action: owner/admin marks one listing request as rejected.
@app.route("/reject-request/<int:id>", methods=["POST"])
def reject_request(id):

    if "user_id" not in session:
        return redirect("/login")

    if not is_owner_or_admin():
        return redirect("/")

    conn = db()
    cursor = conn.cursor(dictionary=True)

    if is_admin():
        cursor.execute("""
            UPDATE requests
            SET status='rejected'
            WHERE id=%s
        """, (id,))
    else:
        cursor.execute("""
            UPDATE requests
            JOIN listings ON requests.listing_id = listings.id
            SET requests.status='rejected'
            WHERE requests.id=%s
            AND listings.owner_id=%s
        """, (id, session["user_id"]))

    updated = cursor.rowcount

    push_target = None
    if updated:
        cursor.execute("""
            SELECT requests.user_id, listings.title AS listing_title
            FROM requests
            JOIN listings ON requests.listing_id = listings.id
            WHERE requests.id=%s
        """, (id,))
        push_target = cursor.fetchone()

    conn.commit()
    conn.close()

    if push_target:
        send_web_push_to_user(
            push_target["user_id"],
            push_payload(
                "Request rejected",
                f"Your request for {push_target['listing_title']} was rejected.",
                "/my-requests",
                "request_rejected"
            )
        )

    if not updated:
        if wants_json_response():
            return jsonify({"error": "Request not found or not allowed"}), 404

        return redirect("/requests")

    if wants_json_response():
        return jsonify({"status": "rejected"})

    return redirect("/requests")




# Delete listing action: owner/admin removes a listing and its stored images.
@app.route("/delete/<int:id>", methods=["POST"])
def delete_listing(id):

    if "user_id" not in session:
        return redirect("/login")

    if not is_owner_or_admin():
        return redirect("/")

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT owner_id
        FROM listings
        WHERE id=%s
    """, (id,))

    listing = cursor.fetchone()

    if not listing or (not is_admin() and listing["owner_id"] != session["user_id"]):
        conn.close()
        return redirect("/")

    delete_listing_images_from_storage(cursor, id)

    cursor.execute("""
        DELETE FROM listing_images
        WHERE listing_id=%s
    """, (id,))

    cursor.execute("""
        DELETE FROM requests
        WHERE listing_id=%s
    """, (id,))

    cursor.execute("""
        DELETE FROM listings
        WHERE id=%s
    """, (id,))

    conn.commit()
    conn.close()

    if is_admin():
        return redirect("/admin")

    return redirect("/my-listings")


# Admin dashboard route: summarizes users, listings, requests, and moderation signals.
@app.route("/admin")
def admin_dashboard():

    if "user_id" not in session:
        return redirect("/login")

    if not is_admin():
        return redirect("/")

    ensure_listing_filter_columns()

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            COUNT(*) AS total_users,
            SUM(CASE WHEN role='user' THEN 1 ELSE 0 END) AS seekers,
            SUM(CASE WHEN role='owner' THEN 1 ELSE 0 END) AS owners,
            SUM(CASE WHEN role='admin' THEN 1 ELSE 0 END) AS admins
        FROM users
    """)
    user_stats = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) AS total FROM listings")
    total_listings = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM requests")
    total_requests = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT status, COUNT(*) AS total
        FROM requests
        GROUP BY status
    """)
    request_rows = cursor.fetchall()
    request_stats = {row["status"]: row["total"] for row in request_rows}

    cursor.execute("""
        SELECT
            users.*,
            COUNT(DISTINCT listings.id) AS listing_count,
            COUNT(DISTINCT requests.id) AS request_count
        FROM users
        LEFT JOIN listings ON listings.owner_id = users.id
        LEFT JOIN requests ON requests.user_id = users.id
        GROUP BY users.id
        ORDER BY users.id DESC
    """)
    users = cursor.fetchall()

    cursor.execute("""
        SELECT
            listings.*,
            users.name AS owner_name,
            users.email AS owner_email,
            (
                SELECT image
                FROM listing_images
                WHERE listing_images.listing_id = listings.id
                LIMIT 1
            ) AS image
        FROM listings
        LEFT JOIN users ON users.id = listings.owner_id
        ORDER BY listings.id DESC
        LIMIT 12
    """)
    listings = cursor.fetchall()

    conn.close()

    return render_template(
        "admin.html",
        users=users,
        listings=listings,
        user_stats=user_stats,
        total_listings=total_listings,
        total_requests=total_requests,
        request_stats=request_stats
    )


# Admin role update action: changes a user's role between user, owner, and admin.
@app.route("/admin/user/<int:id>/role", methods=["POST"])
def admin_update_user_role(id):

    if "user_id" not in session:
        return redirect("/login")

    if not is_admin():
        return redirect("/")

    role = request.form.get("role")

    if role not in ("user", "owner", "admin"):
        return redirect("/admin")

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        UPDATE users
        SET role=%s
        WHERE id=%s
    """, (role, id))

    conn.commit()
    conn.close()

    if id == session.get("user_id"):
        session["role"] = role

    return redirect("/admin")


# Admin delete user action: removes a user and cleans up their related data safely.
@app.route("/admin/delete-user/<int:id>", methods=["POST"])
def admin_delete_user(id):

    if "user_id" not in session:
        return redirect("/login")

    if not is_admin():
        return redirect("/")

    if id == session.get("user_id"):
        return redirect("/admin")

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT id
        FROM listings
        WHERE owner_id=%s
    """, (id,))
    owned_listings = cursor.fetchall()

    for listing in owned_listings:
        delete_listing_images_from_storage(cursor, listing["id"])

        cursor.execute("""
            DELETE FROM listing_images
            WHERE listing_id=%s
        """, (listing["id"],))

        cursor.execute("""
            DELETE FROM requests
            WHERE listing_id=%s
        """, (listing["id"],))

    cursor.execute("""
        DELETE FROM requests
        WHERE user_id=%s
    """, (id,))

    cursor.execute("""
        DELETE FROM listings
        WHERE owner_id=%s
    """, (id,))

    cursor.execute("""
        DELETE FROM users
        WHERE id=%s
    """, (id,))

    conn.commit()
    conn.close()

    return redirect("/admin")


# Notification feed route: returns new counts/items for the navbar notification UI.
@app.route("/notifications/feed")
def notifications_feed():

    if "user_id" not in session:
        return jsonify({"notifications": []})

    conn = db()
    cursor = conn.cursor(dictionary=True)

    notifications = []
    user_id = session["user_id"]

    if is_owner_or_admin():
        owner_seen_key = "owner_seen_request_id"
        owner_seen_id = session.get(owner_seen_key)

        if is_admin():
            owner_filter = ""
            params = ()
        else:
            owner_filter = "WHERE listings.owner_id=%s"
            params = (user_id,)

        cursor.execute(f"""
            SELECT COALESCE(MAX(requests.id), 0) AS latest_id
            FROM requests
            JOIN listings ON requests.listing_id = listings.id
            {owner_filter}
        """, params)

        latest_owner_request_id = cursor.fetchone()["latest_id"] or 0

        if owner_seen_id is None:
            session[owner_seen_key] = latest_owner_request_id
            owner_seen_id = latest_owner_request_id

        if is_admin():
            new_params = (owner_seen_id,)
            owner_new_filter = "WHERE requests.id > %s"
        else:
            new_params = (user_id, owner_seen_id)
            owner_new_filter = "WHERE listings.owner_id=%s AND requests.id > %s"

        cursor.execute(f"""
            SELECT
                requests.id,
                requests.status,
                users.name AS user_name,
                listings.title AS listing_title
            FROM requests
            JOIN users ON requests.user_id = users.id
            JOIN listings ON requests.listing_id = listings.id
            {owner_new_filter}
            ORDER BY requests.id DESC
            LIMIT 5
        """, new_params)

        for req in cursor.fetchall():
            notifications.append({
                "id": f"owner-{req['id']}",
                "type": "owner_request",
                "title": "New booking request",
                "message": f"{req['user_name']} requested {req['listing_title']}",
                "link": "/requests"
            })

        session[owner_seen_key] = latest_owner_request_id

    cursor.execute("""
        SELECT
            requests.id,
            requests.status,
            listings.title AS listing_title
        FROM requests
        JOIN listings ON requests.listing_id = listings.id
        WHERE requests.user_id=%s
    """, (user_id,))

    user_requests = cursor.fetchall()
    seen_statuses = session.get("user_seen_request_statuses")

    current_statuses = {
        str(req["id"]): req["status"]
        for req in user_requests
    }

    if seen_statuses is None:
        session["user_seen_request_statuses"] = current_statuses
        seen_statuses = current_statuses

    for req in user_requests:
        req_id = str(req["id"])
        old_status = seen_statuses.get(req_id)
        new_status = req["status"]

        if new_status in ("accepted", "rejected") and old_status != new_status:
            notifications.append({
                "id": f"user-{req_id}-{new_status}",
                "type": f"request_{new_status}",
                "title": "Request accepted" if new_status == "accepted" else "Request rejected",
                "message": f"Your request for {req['listing_title']} was {new_status}.",
                "link": "/my-requests"
            })

    session["user_seen_request_statuses"] = current_statuses

    session.modified = True
    conn.close()

    return jsonify({"notifications": notifications})


@app.route("/sw.js")
def service_worker():
    response = make_response(send_from_directory(app.static_folder, "sw.js"))
    response.headers["Content-Type"] = "application/javascript; charset=utf-8"
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.route("/notifications/push/public-key")
def push_public_key():
    return jsonify({
        "enabled": WEB_PUSH_ENABLED,
        "publicKey": VAPID_PUBLIC_KEY if WEB_PUSH_ENABLED else ""
    })


@app.route("/notifications/push/status")
def push_status():
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401

    ensure_push_subscription_columns()

    conn = db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, user_agent, updated_at
        FROM push_subscriptions
        WHERE user_id=%s
        ORDER BY updated_at DESC
    """, (session["user_id"],))
    subscriptions = cursor.fetchall()
    conn.close()

    return jsonify({
        "enabled": WEB_PUSH_ENABLED,
        "server": {
            "hasPublicKey": bool(VAPID_PUBLIC_KEY),
            "hasPrivateKey": bool(VAPID_PRIVATE_KEY),
            "pywebpushInstalled": bool(webpush)
        },
        "subscriptionCount": len(subscriptions),
        "subscriptions": [
            {
                "id": subscription["id"],
                "userAgent": subscription.get("user_agent") or "",
                "updatedAt": str(subscription.get("updated_at") or "")
            }
            for subscription in subscriptions
        ]
    })


@app.route("/notifications/push/test", methods=["POST"])
def test_push_notification():
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401

    result = send_web_push_to_user(
        session["user_id"],
        push_payload(
            "PG Finder test alert",
            "If this appears with the site closed, phone notifications are working.",
            "/my-requests",
            "info"
        )
    )

    return jsonify(result)


@app.route("/notifications/push/subscribe", methods=["POST"])
def subscribe_push_notifications():
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401

    ensure_push_subscription_columns()

    subscription = request.get_json(silent=True) or {}
    endpoint = subscription.get("endpoint")
    keys = subscription.get("keys") or {}
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")

    if not endpoint or not p256dh or not auth:
        return jsonify({"error": "Invalid push subscription"}), 400

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        INSERT INTO push_subscriptions
        (user_id, endpoint, endpoint_hash, p256dh, auth, user_agent)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            user_id=VALUES(user_id),
            endpoint=VALUES(endpoint),
            p256dh=VALUES(p256dh),
            auth=VALUES(auth),
            user_agent=VALUES(user_agent)
    """, (
        session["user_id"],
        endpoint,
        endpoint_hash(endpoint),
        p256dh,
        auth,
        request.headers.get("User-Agent", "")
    ))

    conn.commit()
    conn.close()

    return jsonify({"ok": True, "enabled": WEB_PUSH_ENABLED})


@app.route("/notifications/push/unsubscribe", methods=["POST"])
def unsubscribe_push_notifications():
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401

    ensure_push_subscription_columns()

    subscription = request.get_json(silent=True) or {}
    endpoint = subscription.get("endpoint")

    if not endpoint:
        return jsonify({"error": "Invalid push subscription"}), 400

    conn = db()
    cursor = conn.cursor(dictionary=True)
    delete_push_subscription(cursor, endpoint)
    conn.commit()
    conn.close()

    return jsonify({"ok": True})



# Edit profile route: lets a signed-in user update their name, phone, and password.
@app.route("/edit-profile", methods=["GET", "POST"])
def edit_profile():

    if "user_id" not in session:
        return redirect("/login")

    conn = db()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]

        cursor.execute("""
            UPDATE users
            SET name=%s,
                email=%s,
                phone=%s
            WHERE id=%s
        """, (
            name,
            email,
            phone,
            session["user_id"]
        ))

        conn.commit()

        return redirect("/profile")

    cursor.execute("""
        SELECT * FROM users
        WHERE id=%s
    """, (session["user_id"],))

    user = cursor.fetchone()

    conn.close()

    return render_template(
        "edit_profile.html",
        user=user
    )


# =========================
# SEND REQUEST
# =========================
# Send request action: user sends a booking/contact request for a specific listing.
@app.route("/request/<int:listing_id>", methods=["POST"])
def send_request(listing_id):

    # LOGIN CHECK
    if "user_id" not in session:
        return redirect(f"/login?next=/listing/{listing_id}")

    message = request.form.get("message")
    phone = request.form.get("phone")
    email = request.form.get("email")

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT id, owner_id, title
        FROM listings
        WHERE id=%s
    """, (listing_id,))
    listing = cursor.fetchone()

    if not listing:
        conn.close()
        return render_app_error("Listing not found", "This listing is no longer available.", 404, "Browse listings", "/find")

    if listing["owner_id"] == session["user_id"]:
        conn.close()
        return redirect(f"/listing/{listing_id}?request=own-listing")

    # CHECK EXISTING REQUEST
    cursor.execute("""
        SELECT * FROM requests
        WHERE listing_id=%s
        AND user_id=%s
    """, (
        listing_id,
        session["user_id"]
    ))

    existing = cursor.fetchone()

    # ALREADY SENT
    if existing:

        if existing["status"] == "pending":
            conn.close()
            return redirect(f"/listing/{listing_id}?request=already-pending")

        if existing["status"] == "accepted":
            conn.close()
            return redirect(f"/listing/{listing_id}?request=already-accepted")

        # REJECTED -> ALLOW RESEND
        if existing["status"] == "rejected":

            cursor.execute("""
                UPDATE requests
                SET message=%s,
                    phone=%s,
                    email=%s,
                    status='pending'
                WHERE id=%s
            """, (
                message,
                phone,
                email,
                existing["id"]
            ))

            conn.commit()
            conn.close()

            send_web_push_to_user(
                listing["owner_id"],
                push_payload(
                    "Booking request resent",
                    f"{session.get('username', 'A seeker')} resent a request for {listing['title']}.",
                    "/requests",
                    "owner_request"
                )
            )

            return redirect(f"/listing/{listing_id}?request=resent")

    # NEW REQUEST
    cursor.execute("""
        INSERT INTO requests
        (listing_id, user_id, message, phone, email, status)

        VALUES (%s,%s,%s,%s,%s,%s)
    """, (
        listing_id,
        session["user_id"],
        message,
        phone,
        email,
        "pending"
    ))

    conn.commit()
    conn.close()

    send_web_push_to_user(
        listing["owner_id"],
        push_payload(
            "New booking request",
            f"{session.get('username', 'A seeker')} requested {listing['title']}.",
            "/requests",
            "owner_request"
        )
    )

    return redirect(f"/listing/{listing_id}?request=sent")


# =========================
# EDIT LISTING
# =========================
# Edit listing route: owner/admin updates listing details, location, amenities, and images.
@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_listing(id):

    ensure_listing_filter_columns()

    # LOGIN CHECK
    if "user_id" not in session:
        return redirect("/login")

    if not is_owner_or_admin():
        return redirect("/")

    conn = db()
    cursor = conn.cursor(dictionary=True)

    # GET LISTING
    cursor.execute("""
        SELECT * FROM listings
        WHERE id=%s
    """, (id,))

    listing = cursor.fetchone()

    if not listing or (not is_admin() and listing["owner_id"] != session["user_id"]):
        conn.close()
        return redirect("/")

    cursor.execute("""
        SELECT *
        FROM listing_images
        WHERE listing_id=%s
    """, (id,))

    images = cursor.fetchall()

    # UPDATE
    if request.method == "POST":

        listing_form, form_error = clean_listing_form(
            request.form,
            listing.get("latitude"),
            listing.get("longitude")
        )
        files = [
            file for file in request.files.getlist("images")
            if file and file.filename
        ]

        if form_error:
            conn.close()
            return render_app_error("Listing needs one fix", form_error, 400, "Back to Edit Listing", f"/edit/{id}")

        if len(files) > MAX_LISTING_IMAGES:
            conn.close()
            return render_app_error(
                "Too many photos",
                f"Please upload up to {MAX_LISTING_IMAGES} images per listing.",
                400,
                "Back to Edit Listing",
                f"/edit/{id}"
            )

        saved_images = []

        try:
            cursor.execute("""
                UPDATE listings

                SET
                title=%s,
                price=%s,
                rent_period=%s,
                room_type=%s,
                sharing_type=%s,
                amenities=%s,
                location=%s,
                description=%s,
                latitude=%s,
                longitude=%s

                WHERE id=%s
            """, (
                listing_form["title"],
                listing_form["price"],
                listing_form["rent_period"],
                listing_form["room_type"],
                listing_form["sharing_type"],
                listing_form["amenities"],
                listing_form["location"],
                listing_form["description"],
                listing_form["latitude"],
                listing_form["longitude"],
                id
            ))

            if files:
                delete_listing_images_from_storage(cursor, id)

                cursor.execute("""
                    DELETE FROM listing_images
                    WHERE listing_id=%s
                """, (id,))

                for file in files:
                    filename = save_uploaded_image(file)

                    if filename:
                        saved_images.append(filename)
                        cursor.execute("""
                            INSERT INTO listing_images
                            (listing_id, image)

                            VALUES (%s,%s)
                        """, (id, filename))

            conn.commit()
        except Exception:
            conn.rollback()

            for image in saved_images:
                delete_stored_image(image)

            conn.close()
            raise

        conn.close()

        return redirect("/my-listings")

    conn.close()

    return render_template(
        "edit_listing.html",
        listing=listing,
        images=images
    )

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
