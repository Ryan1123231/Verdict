# Verdict

A social rating app for films, shows, and games, built primarily as an exercise in designing and testing an authorization layer.

**Live:** [verdictapp.app](https://verdictapp.app)  
**Stack:** FastAPI · PostgreSQL · SQLAlchemy · Alembic · Jinja2 · Docker Compose  
**Author:** Ryan Dempsey, Integrated Information Technology with a Cybersecurity Operations minor, University of South Carolina

---

## Why this exists

I wanted a project where authorization was the hard part, not an afterthought.

Most CRUD apps get authentication right and authorization wrong. Logging in is a solved problem. Every framework hands it to you. Deciding whether *this* logged-in user is allowed to touch *that* specific row is where real bugs live, and it's the class of bug I'd been finding from the attacker's side during a security assessment at my internship. Building the defender's version of the same problem seemed like the fastest way to actually understand it.

So the app is a real app. My friends use it. But every feature was chosen partly because it creates an authorization question worth answering:

- Ratings belong to one user. Can someone edit yours?
- Friendships are bidirectional and stateful. Can you approve a request sent *to* you, or also one you sent?
- Profiles are private by default. Can you read someone's ratings before they accept you?
- Avatars are user-uploaded files. What happens if the file isn't an image?

Every one of those got implemented, then attacked, then documented below.

---

## Security design

### Object-level authorization

The core decision: **ownership is part of the query, never a separate check.**

The wrong version, which is how most IDOR bugs get written:

```python
rating = db.get(Rating, rating_id)   # fetched by ID alone
rating.score = score                 # no ownership check
```

The version in this codebase:

```python
rating = db.scalar(
    select(Rating).where(Rating.id == rating_id, Rating.user_id == user.id)
)
if rating is None:
    raise HTTPException(status_code=404, detail="Rating not found")
```

There's no ownership check that can be forgotten, because there is no ownership check. Ownership is a `WHERE` clause. Every route touching `ratings`, `friendships`, or user media follows this shape.

**404, not 403.** A 403 confirms the resource exists and belongs to someone else, which lets an attacker enumerate valid IDs. A 404 is indistinguishable from a resource that never existed. Both cases hit the same code path.

### Sessions

Signed cookies via `itsdangerous`, not JWTs. The payload is `{"uid": <int>}`, HMAC-signed with a server-side secret.

- `__Host-` prefix. The browser refuses the cookie unless it's `Secure`, has no `Domain` attribute, and `Path=/`. Enforced by the browser, not by application code.
- `HttpOnly`. JavaScript can't read it, so an XSS bug can't become session theft.
- `SameSite=Lax`. The browser won't attach it to cross-site POSTs, which handles the common CSRF cases.
- The payload is readable but not forgeable. Anyone can base64-decode their own user ID. Nobody can change it.

**Tradeoff, stated plainly:** stateless signed cookies can't be revoked. There is no "log out everywhere," and changing a password doesn't invalidate sessions on other devices. Fixing this means a session table or a per-user token version. It's listed under Known Limitations for a reason.

### Passwords

Argon2id via `argon2-cffi`, at the library's defaults of 64 MiB memory, 3 iterations, 4 lanes. Memory-hard, so GPU cracking rigs don't get the speedup they enjoy against bcrypt or the SHA family. Parameters are encoded in the stored hash, so they can be raised later without breaking existing logins.

Login returns an identical error for "no such account" and "wrong password". Different messages let someone enumerate which emails are registered.

Uniqueness is enforced by catching `IntegrityError` on the database constraint, not by a pre-flight `SELECT`. A check-then-insert has a race window; a unique index does not.

### File uploads

Avatars and backdrops are the most dangerous input the app accepts. The pipeline never trusts the upload:

1. **Size cap before anything else.** 4 MB, checked on the raw bytes.
2. **Decode, don't sniff.** `Content-Type` is attacker-controlled and ignored. Pillow's `verify()` runs first; anything that isn't a real image raises and gets dropped.
3. **`Image.MAX_IMAGE_PIXELS`** caps decompression bombs. A 2 KB PNG that expands to gigabytes fails before it allocates.
4. **Re-encode from decoded pixels.** The stored file is written fresh as JPEG from the decoded pixel data. Any polyglot payload, embedded script, or EXIF weirdness in the original does not survive this step. This is the control that matters most.
5. **Generated filename.** The user's filename is discarded entirely; the stored name comes from `secrets.token_urlsafe`. No path traversal, no `.php`, no collisions.
6. **Stored outside the application directory**, in a Docker volume mounted at `/media` and served as static files.

### Input validation

Every user-controlled value that reaches a query, a redirect, or an external API is validated against a whitelist rather than sanitized against a blacklist.

| Input | Control |
|---|---|
| `?type=` and `?sort=` on list pages | Lookup tables; unknown keys fall through to a default. The user's string never becomes part of a query. |
| `/browse/{kind}` | Whitelist check before the value reaches an API call. |
| `?limit=` on the feed | Clamped server-side to a range of 1 to 100. Uncapped pagination is a DoS vector. |
| Rating scores | Bounds-checked server-side. Client-side validation is UX, not a control. |
| Usernames | Regex whitelist `[A-Za-z0-9_.-]{3,32}`. Blocks homoglyph and zero-width-space impersonation. |
| IGDB search terms | Double quotes stripped. IGDB's APIcalypse wraps search terms in quotes, so this is query injection in a non-SQL query language. |
| IGDB item IDs | Coerced to `int` before interpolation, since the query syntax takes a bare unquoted number. |
| Redirect targets after rating | Must start with a single `/`. Rejects absolute URLs and protocol-relative `//evil.com`. Prevents open redirect. |
| Scroll anchors | Non-alphanumerics stripped before entering the `Location` header, preventing response splitting. |

### Preventing mass assignment

When a user rates something, they send only `media_type` and `source_id`. Title, year, and poster URL are re-fetched from TMDB or IGDB server-side.

If the endpoint accepted a `title` parameter, any user could inject arbitrary text into the shared `items` table, text that then renders on every other user's feed.

### Output encoding

Jinja2 autoescapes by default, which covers all server-rendered pages. The search page builds cards in JavaScript, where that protection does not apply, so it has its own `esc()` function applied to every field. Titles come from third-party APIs, which is exactly the data you don't control.

There is exactly one `|safe` in the codebase, on the friends list, wrapping usernames in `<b>` tags. Usernames are regex-constrained to 32 alphanumeric characters, so it's safe, but it's the filter that turns autoescaping off, and it's worth knowing where it lives.

### Rate limiting

`slowapi`, keyed on `CF-Connecting-IP` rather than the socket address. Every request arrives from Cloudflare's edge, so without this every user would share one bucket.

- Login: 8/minute
- Registration: 4/hour
- Password change: 6/hour
- Account deletion: 3/hour

### Deployment

- **Cloudflare Tunnel.** The tunnel dials outward; no inbound ports are opened on the network. There is no port forwarding rule anywhere.
- **TLS terminated at Cloudflare.** The `.app` TLD is on the HSTS preload list, so browsers refuse plain HTTP for the domain at the protocol level.
- **App bound to `127.0.0.1:8000`** inside the VM. Reachable by the tunnel, not by anything else on the LAN.
- **Postgres bound to loopback**, reachable only over Docker's internal network. Never exposed.
- **Secrets in `.env`**, gitignored before the file was ever created. No credential has been committed at any point in the repo's history.
- **No source mount in production.** The image is built from source rather than reading live files, which is why code changes require a rebuild rather than a restart.

---

## Security testing

I attacked my own app. These are real transcripts, not descriptions.

### 1. Session cookie tampering

The payload is base64 and readable. Decoding `eyJ1aWQiOjF9` gives `{"uid":1}`. Modifying it to `{"uid":2}` produces `eyJ1aWQiOjJ9`, same signature, different claim.

```
$ curl -s https://verdictapp.app/ -H "Cookie: session=eyJ1aWQiOjF9.2Ytz6Au6D0Tc33d6Z14OIaDqqi4"
{"logged_in":true,"username":"ryan"}

$ curl -s https://verdictapp.app/ -H "Cookie: session=eyJ1aWQiOjJ9.2Ytz6Au6D0Tc33d6Z14OIaDqqi4"
{"logged_in":false}
```

**Result:** HMAC verification fails, `read_session` returns `None`, request is treated as anonymous. Horizontal privilege escalation via session manipulation: blocked.

### 2. Cross-user rating modification (IDOR)

Rating ID 1 belongs to user 1. Attempted with user 2's session.

```
$ curl -s -i -X PUT https://verdictapp.app/ratings/1 \
    -H "Cookie: session=<user2>" -d "score=1" -d "review=pwned"
HTTP/1.1 404 Not Found
{"detail":"Rating not found"}

$ curl -s -i -X DELETE https://verdictapp.app/ratings/1 \
    -H "Cookie: session=<user2>"
HTTP/1.1 404 Not Found
{"detail":"Rating not found"}
```

Verified the state actually held, using user 1's session:

```
$ curl -s https://verdictapp.app/ratings/me -H "Cookie: session=<user1>"
{"ratings":[{"id":1,"item_id":1,"score":10,"review":null,
"created_at":"2026-08-20T03:29:57.270777+00:00",
"updated_at":"2026-08-20T03:30:27.224350+00:00"}]}
```

**Result:** Both writes rejected. `updated_at` is unchanged from before the attack, so the 404 was a real rejection and not a cosmetic error message.

### 3. Business-logic authorization: self-approving a friend request

This is the more interesting one, because the row *does* belong to the attacker in the ordinary sense. They created it. Ownership isn't the permission that matters; being the *addressee* is.

```
 id | requester_id | addressee_id |  status
----+--------------+--------------+---------
  3 |            1 |            3 | pending
```

User 1 sent the request. User 1 attempts to accept it:

```
$ curl -s -i -X POST https://verdictapp.app/api/friends/3/accept \
    -H "Cookie: session=<user1>"
HTTP/1.1 404 Not Found
{"detail":"Request not found"}
```

State afterward:

```
 id | status
----+---------
  3 | pending
```

**Result:** Rejected. A row-ownership check would have permitted this. Only scoping the lookup to `addressee_id == user.id` catches it.

### 4. Data isolation before friendship

User 2 rated an item. User 1's feed, while not yet friends:

```
$ curl -s https://verdictapp.app/feed -H "Cookie: session=<user1>"
{"feed":[]}
```

After the friendship is accepted, the same rating appears.

**Result:** Isolation holds by default. The authorization is the join itself. There is no post-filter to forget.

### 5. Stored XSS in review text

Submitted `<script>alert('xss')</script>` as a review body. The payload persists in the database and renders on the profile page, the feed, and any friend's view of it.

**Result:** Rendered as literal text. Page source shows `&lt;script&gt;`. Jinja2 autoescaping applied at render time, not sanitized at input. The raw string is preserved in storage and neutralized on output, which is the correct order.

### 6. Rate limiting

Ten sequential failed logins from one IP:

```
$ for i in $(seq 1 10); do
    curl -s -o /dev/null -w "%{http_code} " -X POST https://verdictapp.app/ui/login \
      -d "email=nobody@test.com" -d "password=wrongpassword"
  done

401 401 401 401 401 401 401 401 429 429
```

**Result:** Exactly eight attempts before the limiter engages, matching the configured `8/minute`. Verified through the tunnel with real client IPs.

---

## Known limitations

I'd rather list these than have someone find them.

**Sessions cannot be revoked.** Stateless signed cookies mean no "log out everywhere," and a password change doesn't invalidate sessions elsewhere. Fixing this properly requires a session table or a per-user token version bumped on credential change.

**Backups share a disk with the database.** A nightly `pg_dump` runs with a size assertion so it fails loudly rather than silently producing an empty file, but both copies live on the same SSD. This protects against `DROP TABLE` and bad migrations, not hardware failure. Off-site copies to S3 are the obvious next step.

**Hosted on a desktop.** Availability is bounded by a Dell staying powered on. A Windows update at 3am takes the site down until someone notices. This is a deliberate tradeoff for a project of this size, not an accident, but it isn't production infrastructure.

**No CSRF tokens.** Protection relies entirely on `SameSite=Lax`, which covers modern browsers but is a single control where defense in depth would use two.

**No email verification.** Registration accepts any well-formed address. Anyone can sign up as anyone.

**`CF-Connecting-IP` is trusted.** Correct behind Cloudflare, since the app is unreachable except through the tunnel, but the header itself isn't cryptographically bound to anything.

**Cleartext between tunnel and app.** `cloudflared` reaches uvicorn over plain HTTP on loopback inside the VM. Low risk given nothing else can reach that port, but it's not encrypted end to end.

**No automated test suite.** The security testing above was manual and reproducible, but nothing prevents a future change from silently breaking an authorization check. This is the gap I'd close first.

---

## The application

Verdict lets a small group of friends rate films, shows, and games in one place, and see what everyone else thought.

**Content.** Search spans TMDB (films and TV) and IGDB (games) simultaneously, with debounced live results as you type. Selecting something caches canonical metadata locally, so the app doesn't depend on either API being up to render a page.

**Ratings.** 1 to 10 with an optional review. Rating something twice updates rather than duplicates, enforced by a unique constraint on `(user_id, item_id)`. Anything you've already rated shows your score inline wherever it appears, with the form pre-filled.

**Friends.** Bidirectional requests with pending and accepted states. Sending a request to someone who already requested you auto-accepts. Self-friending is blocked by a database `CHECK` constraint, not just application code.

**Feed and profiles.** The feed shows friends' recent ratings. Profiles are friends-only by default, with an opt-in public toggle, and support a custom avatar, backdrop, and bio. Ratings on any profile filter by type and sort seven ways.

**Discover and browse.** Trending films and shows from TMDB, popular games from IGDB, cached for an hour so page loads don't hammer either API. Anything you or a friend has rated is tagged inline. Each section expands to a paginated browse page.

**Schema.** Four core tables. `items` holds all three media types with a `source` and `type` column rather than separate tables per format, which is why adding IGDB required zero schema changes.

---

## Running it

```bash
git clone https://github.com/RyanDempsey05/Verdict.git
cd Verdict
```

Create `.env`:

```
POSTGRES_PASSWORD=<generate one>
SECRET_KEY=<python3 -c "import secrets; print(secrets.token_urlsafe(48))">
TMDB_TOKEN=<TMDB API Read Access Token>
TWITCH_CLIENT_ID=<Twitch developer console>
TWITCH_CLIENT_SECRET=<Twitch developer console>
```

```bash
docker compose up -d --build
docker compose exec app alembic upgrade head
```

Runs on `127.0.0.1:8000`. IGDB access goes through Twitch's client-credentials flow; the token is cached in-process and refreshed 5 minutes before expiry, with a lock so concurrent requests don't each trigger a refresh.

---

## What I'd do next

In order of what I think matters most:

1. **Automated tests for the authorization layer.** Every transcript above should be a test that fails loudly if someone breaks it.
2. **Revocable sessions.** A `token_version` column bumped on password change is the cheap version.
3. **Off-site backups.** The script already exists; it just needs an S3 target.
4. **Security headers.** CSP, `X-Frame-Options`, and `Referrer-Policy` are currently absent.
5. **Email verification** on registration.

---

Built by [Ryan Dempsey](https://github.com/RyanDempsey05).
