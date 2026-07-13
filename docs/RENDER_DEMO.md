# Free Render Demo — Funduqii

This guide deploys a **free, temporary** copy of Funduqii on
[Render](https://render.com) so you can show the app to hotels and collect
feedback. It is **not** production: it uses sample data, sleeps when idle, and
the free database expires after about 30 days.

The `render.yaml` Blueprint at the repository root provisions everything:

| Resource | Name | Plan | What it is |
| --- | --- | --- | --- |
| PostgreSQL | `funduqii-demo-db` | free | The demo database |
| Web (Python) | `funduqii-demo-api` | free | Django API (gunicorn) |
| Web (Node) | `funduqii-demo-web` | free | Next.js frontend |

Predictable public URLs (from the service names):

- API: `https://funduqii-demo-api.onrender.com`
- App: `https://funduqii-demo-web.onrender.com`  ← share this one with hotels

---

## Steps

### 1. Get the branch onto GitHub
Push (or merge, per your process) the branch that contains `render.yaml` to your
GitHub repository. Render reads the Blueprint from the branch you pick in step 3.

### 2. Create / log in to a Render account
Go to <https://render.com>, sign up (the free tier needs no card), and connect
your GitHub account so Render can see this repository.

### 3. Create the Blueprint
In the Render dashboard: **New + → Blueprint**. Choose this GitHub repository,
then select the **branch** that has `render.yaml`. Render reads the Blueprint and
shows the three resources it will create (the database and the two web services).
Click **Apply** to provision them.

- `SECRET_KEY` is generated automatically by Render (`generateValue`).
- `DATABASE_URL` is wired automatically from `funduqii-demo-db`.
- No secrets are stored in the repository.

### 4. Wait for both services to build and deploy
The first build takes several minutes (installing dependencies, `collectstatic`,
`migrate` for the API; `npm ci` + `next build` for the web). Wait until both
`funduqii-demo-api` and `funduqii-demo-web` show **Live**.

### 5. Seed the demo data (one time)
Open the **`funduqii-demo-api`** service → **Shell** tab, and run:

```bash
python manage.py seed_demo
```

This is idempotent — safe to run again if needed. It creates one active demo
hotel (currency USD), floors, varied room types, rooms in every operational
state, and two logins. It prints the credentials at the end:

| Role | Email | Password | Access |
| --- | --- | --- | --- |
| Manager | `manager@demo.funduqii.app` | `Demo12345!` | Full access |
| Front desk | `frontdesk@demo.funduqii.app` | `Demo12345!` | Read-only (`rooms.view`) |

> These are throwaway demo credentials for sample data — never reuse them for
> anything real.

### 6. Open the app and log in
Open <https://funduqii-demo-web.onrender.com> and sign in with the **Manager**
credentials above.

### 7. Share with hotels
Send hotels the app URL (<https://funduqii-demo-web.onrender.com>) so they can
click around and give feedback.

---

## Free-tier caveats (tell your audience)

- **Cold starts:** free web services **sleep after ~15 minutes** of no traffic.
  The first request after sleep takes **~50 seconds** to wake up — this is
  normal for the free tier, not a bug. Following requests are fast.
- **Database expiry:** the free PostgreSQL is deleted after **~30 days**. Re-run
  the Blueprint and `seed_demo` to start fresh.
- **Realtime is degraded:** there is no Redis/worker on the free tier, so
  background tasks run inline and live/WebSocket updates degrade gracefully
  (single process). Fine for a demo, not for production load.
- **Sample data only:** this is demo data, not a production deployment.

---

## If you rename the services

The two service names drive two URLs that must stay in sync inside
`render.yaml`. If you change a name, update the matching env var before applying:

- Rename `funduqii-demo-web` → update **`API_INTERNAL_BASE_URL`** on the API
  service and **`CORS_ALLOWED_ORIGINS`** to the new web URL.
- Rename `funduqii-demo-api` → update **`API_INTERNAL_BASE_URL`** on the web
  service to `https://<new-api-name>.onrender.com/api`.

`ALLOWED_HOSTS` uses the wildcard `.onrender.com`, so it does **not** need
changing when you rename services.
