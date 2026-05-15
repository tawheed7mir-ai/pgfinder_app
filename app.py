# =========================
# FULL MYSQL UPDATED app.py
# =========================

from flask import Flask, render_template, request, redirect, session, flash, jsonify, make_response, abort
import mysql.connector
import requests
import os
import math
import secrets
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash


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
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

if os.environ.get("FLASK_ENV") == "production" and app.secret_key == "dev-only-change-me":
    raise RuntimeError("SECRET_KEY must be set in production")

if os.environ.get("FLASK_ENV") == "production" and not os.environ.get("DB_PASSWORD"):
    raise RuntimeError("DB_PASSWORD must be set in production")

UPLOAD_FOLDER = "static/images"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_CONTENT_LENGTH", 8 * 1024 * 1024))

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "avif"}

INDIA_MAP_CENTER = {
    "lat": 22.9734,
    "lng": 78.6569
}


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


def db():
    config, database_name = db_config()

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
            image VARCHAR(255) NOT NULL
        )
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

    conn.commit()
    conn.close()


def csrf_token():
    token = session.get("_csrf_token")

    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token

    return token


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": csrf_token}


@app.before_request
def protect_post_requests():
    if request.method != "POST":
        return

    expected = session.get("_csrf_token")
    submitted = request.form.get("_csrf_token") or request.headers.get("X-CSRFToken")

    if not expected or not submitted or not secrets.compare_digest(expected, submitted):
        abort(400, "Invalid CSRF token")


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

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    filename = secure_filename(file.filename)
    name, extension = os.path.splitext(filename)
    unique_filename = f"{name[:60]}-{secrets.token_hex(8)}{extension.lower()}"
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_filename))

    return unique_filename


def is_owner_or_admin():
    return session.get("role") in ("owner", "admin")


def is_admin():
    return session.get("role") == "admin"


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

    url = f"https://nominatim.openstreetmap.org/search?q={place}&format=json"

    headers = {
        "User-Agent": "PGFinder"
    }

    response = requests.get(url, headers=headers)

    data = response.json()

    if data:

        latitude = data[0]["lat"]
        longitude = data[0]["lon"]

        return latitude, longitude

    return None, None


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
        "User-Agent": "PGFinder India location search"
    }

    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers=headers,
            timeout=6
        )
        response.raise_for_status()
        places = response.json()
    except requests.RequestException:
        return jsonify({"error": "Unable to search locations"}), 502

    results = []

    for place in places:

        display_name = place.get("display_name", "")

        results.append({
            "name": display_name,
            "lat": place.get("lat"),
            "lon": place.get("lon"),
            "type": place.get("type", "place")
        })

    return jsonify(results)


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
        "User-Agent": "PGFinder India reverse geocoding"
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
@app.route("/")
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
        where_clauses.append("CAST(price AS UNSIGNED) <= %s")
        params.append(7000)
    elif category_filter == "premium":
        where_clauses.append("CAST(price AS UNSIGNED) BETWEEN %s AND %s")
        params.extend([10000, 20000])
    elif category_filter == "luxury":
        where_clauses.append("CAST(price AS UNSIGNED) > %s")
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
        where_clauses.append("CAST(price AS UNSIGNED) >= %s")
        params.append(min_price)

    if max_price:
        where_clauses.append("CAST(price AS UNSIGNED) <= %s")
        params.append(max_price)

    order_by = "id DESC"

    if sort == "price_low":
        order_by = "CAST(price AS UNSIGNED) ASC"
    elif sort == "price_high":
        order_by = "CAST(price AS UNSIGNED) DESC"

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

    limited_data = data if filters_active or nearby_active else data[:4]

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        response = make_response(render_template(
            "listings_partial.html",
            data=limited_data
        ))
        response.headers["X-Total-Count"] = str(len(data))
        return response

    return render_template(

        "home.html",

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

        user=user,

        uid=session.get("user_id")

    )


# =========================
# SIGNUP
# =========================
@app.route("/signup", methods=["GET", "POST"])
def signup():

    ensure_user_auth_columns()

    if request.method == "POST":

        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        phone = request.form["phone"]
        role = request.form["role"]

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
@app.route('/login', methods=['GET', 'POST'])
def login():

    ensure_user_auth_columns()

    if "user_id" in session:
        next_url = request.args.get("next") or "/"

        if not next_url.startswith("/"):
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

            session['user_id'] = user['id']
            session['username'] = user['name']
            session['role'] = user['role']
            initialize_notification_state(user["id"], user["role"])

            if not next_url.startswith("/"):
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
        return "❌ User not found"

    # OWNER CHECK
    if user["role"] not in ("owner", "admin"):

        conn.close()

        return """
        <h2 style="text-align:center;margin-top:100px;color:red;">
            ❌ Only Owners Can Add Listings
        </h2>
        """

    # POST
    if request.method == "POST":

        title = request.form["title"]
        price = request.form["price"]
        room_type = request.form.get("room_type", "")
        sharing_type = request.form.get("sharing_type", "")
        amenities = ",".join(request.form.getlist("amenities"))
        location = request.form["location"]
        description = request.form["description"]
        files = [
            file for file in request.files.getlist("images")
            if file and file.filename
        ]

        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")

        if not latitude or not longitude:

            conn.close()

            return "❌ Please select location from map"

        cursor.execute("""
            INSERT INTO listings
            (
                title, price, room_type, sharing_type, amenities,
                location, description, latitude, longitude, owner_id
            )

            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            title,
            price,
            room_type,
            sharing_type,
            amenities,
            location,
            description,
            latitude,
            longitude,
            session["user_id"]
        ))

        conn.commit()

        listing_id = cursor.lastrowid

        for file in files:

            filename = save_uploaded_image(file)

            if filename:
                cursor.execute("""
                    INSERT INTO listing_images
                    (listing_id, image)

                    VALUES (%s,%s)
                """, (listing_id, filename))

        conn.commit()
        conn.close()

        return redirect("/")

    conn.close()

    return render_template("add_listing.html")

# =========================
# CATEGORY FILTER
# =========================
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

        cursor.execute("""
            SELECT * FROM listings
            WHERE CAST(price AS UNSIGNED) > 20000
            ORDER BY id DESC
        """)

    elif name == "budget":

        cursor.execute("""
            SELECT * FROM listings
            WHERE CAST(price AS UNSIGNED) <= 7000
            ORDER BY id DESC
        """)

    elif name == "premium":

        cursor.execute("""
            SELECT * FROM listings
            WHERE CAST(price AS UNSIGNED)
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
        "home.html",
        data=data[:4],
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
        "home.html",
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
@app.route("/listing/<int:id>")
def listing_detail(id):

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
        return "❌ Listing not found"

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

@app.route("/my-listings")
def my_listings():

    if "user_id" not in session:
        return redirect("/login")

    if not is_owner_or_admin():
        return redirect("/")

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


@app.route("/my-requests")
def my_requests():

    if "user_id" not in session:
        return redirect("/login")

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            requests.*,
            listings.title,
            listings.location,
            listings.price,
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

    conn.commit()
    conn.close()

    return redirect("/requests")


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

    conn.commit()
    conn.close()

    return "", 204




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


@app.route("/admin")
def admin_dashboard():

    if "user_id" not in session:
        return redirect("/login")

    if not is_admin():
        return redirect("/")

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
                "link": "/profile"
            })

    session["user_seen_request_statuses"] = current_statuses

    session.modified = True
    conn.close()

    return jsonify({"notifications": notifications})



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

    return redirect(f"/listing/{listing_id}?request=sent")


# =========================
# EDIT LISTING
# =========================
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

    # LISTING NOT FOUND
    if not listing:

        conn.close()

        return "❌ Listing not found"

    # SECURITY CHECK
    if not is_admin() and listing["owner_id"] != session["user_id"]:

        conn.close()

        return """
        <h2 style='text-align:center;margin-top:100px;color:red;'>
            ❌ Unauthorized Access
        </h2>
        """

    cursor.execute("""
        SELECT *
        FROM listing_images
        WHERE listing_id=%s
    """, (id,))

    images = cursor.fetchall()

    # UPDATE
    if request.method == "POST":

        title = request.form["title"]
        price = request.form["price"]
        room_type = request.form.get("room_type", "")
        sharing_type = request.form.get("sharing_type", "")
        amenities = ",".join(request.form.getlist("amenities"))
        location = request.form["location"]
        description = request.form["description"]
        files = [
            file for file in request.files.getlist("images")
            if file and file.filename
        ]

        cursor.execute("""
            UPDATE listings

            SET
            title=%s,
            price=%s,
            room_type=%s,
            sharing_type=%s,
            amenities=%s,
            location=%s,
            description=%s

            WHERE id=%s
        """, (
            title,
            price,
            room_type,
            sharing_type,
            amenities,
            location,
            description,
            id
        ))

        if files:

            for image in images:

                cursor.execute("""
                    SELECT COUNT(*) AS total
                    FROM listing_images
                    WHERE image=%s
                    AND listing_id<>%s
                """, (image["image"], id))

                used_elsewhere = cursor.fetchone()["total"]
                image_path = os.path.join(app.config["UPLOAD_FOLDER"], image["image"])

                if not used_elsewhere and os.path.exists(image_path):
                    os.remove(image_path)

            cursor.execute("""
                DELETE FROM listing_images
                WHERE listing_id=%s
            """, (id,))

            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

            for file in files:

                filename = save_uploaded_image(file)

                if filename:
                    cursor.execute("""
                        INSERT INTO listing_images
                        (listing_id, image)

                        VALUES (%s,%s)
                    """, (id, filename))

        conn.commit()
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
