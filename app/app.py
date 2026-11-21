import os
import string

from flask import Flask, request, redirect, jsonify
import redis
import psycopg2

app = Flask(__name__)

ALPHABET = string.digits + string.ascii_lowercase + string.ascii_uppercase

cache = redis.Redis(
	host=os.environ.get("REDIS_HOST","redis"),
	port=int(os.environ.get("REDIS_PORT", 6379)),
	decode_responses=True,
)

def get_db():
	"""Connect to PostgreSQL for permanent storage"""
	return psycopg2.connect(
		host=os.environ.get("POSTGRES_HOST", "db"),
		database=os.environ.get("POSTGRES_DB", "urlshortener"),
		user=os.environ.get("POSTGRES_USER", "postgres"),
		password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
	)

def base62_encode(num):
    """Convert a database ID into a short alphanumeric string."""
    if num == 0:
        return ALPHABET[0]
    result = []
    while num > 0:
        num, remainder = divmod(num, 62)
        result.append(ALPHABET[remainder])
    return "".join(reversed(result))


def base62_decode(code):
    """Convert a short code back into the original database ID."""
    num = 0
    for char in code:
        num = num * 62 + ALPHABET.index(char)
    return num

@app.route("/shorten", methods=["POST"])
def shorten_url():
    # Grab the long URL from the request body
    data = request.get_json()
    if not data or "url" not in data:
        return jsonify({"error": "Missing url field"}), 400

    long_url = data["url"]

    conn = get_db()
    cur = conn.cursor()

    # Reuse an existing short ID if this long URL was already shortened
    cur.execute("SELECT id FROM urls WHERE long_url = %s", (long_url,))
    row = cur.fetchone()

    if row:
        url_id = row[0]
        created = False
    else:
        # New URL - insert and let PostgreSQL assign an auto-incrementing ID
        # UNIQUE on long_url also blocks race-condition duplicates
        cur.execute(
            "INSERT INTO urls (long_url) VALUES (%s) ON CONFLICT (long_url) DO NOTHING RETURNING id",
            (long_url,),
        )
        inserted = cur.fetchone()
        if inserted:
            url_id = inserted[0]
            created = True
        else:
            # Another request inserted the same URL between our SELECT and INSERT
            cur.execute("SELECT id FROM urls WHERE long_url = %s", (long_url,))
            url_id = cur.fetchone()[0]
            created = False
        conn.commit()

    cur.close()
    conn.close()

    # Encode the database ID into a short code
    short_code = base62_encode(url_id)

    # Cache the mapping for fast redirects later
    cache.set(short_code, long_url)

    status = 201 if created else 200
    return jsonify({"short_url": f"http://localhost:5000/{short_code}", "short_code": short_code}), status


@app.route("/<short_code>")
def redirect_url(short_code):
    # Check the fast cache first
    long_url = cache.get(short_code)

    if long_url:
        print("CACHE HIT", flush=True)
        return redirect(long_url, code=302)

    # Cache miss - fall back to the database
    print("CACHE MISS - querying database", flush=True)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT long_url FROM urls WHERE id = %s", (base62_decode(short_code),))
    result = cur.fetchone()
    cur.close()
    conn.close()

    if not result:
        return jsonify({"error": "Short URL not found"}), 404

    # Found it in the database - cache it for next time
    long_url = result[0]
    cache.set(short_code, long_url)

    return redirect(long_url, code=302)

@app.route("/health")
def health():
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
