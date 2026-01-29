# Hosted Database Setup Guide

## Option 1: Render PostgreSQL (Recommended - Free Forever)

### Step 1: Create PostgreSQL Database

1. Go to https://dashboard.render.com/register
2. Sign up with GitHub/Google
3. Click **New +** → **PostgreSQL**
4. Fill in:
   - **Name**: `eld-trip-planner-db`
   - **Database**: `eld_trip_planner`
   - **User**: `eld_user`
   - **Region**: Oregon (US West) or Frankfurt (EU)
   - **PostgreSQL Version**: 16
   - **Plan**: **Free** (500 MB, good for ~50k trips)
5. Click **Create Database**

### Step 2: Get Connection Details

After creation, you'll see:
- **Internal Database URL** (use this for Render web services)
- **External Database URL** (use this for local testing)

Example:
```
postgres://eld_user:abc123xyz@dpg-xxxxx-a.oregon-postgres.render.com/eld_trip_planner
```

### Step 3: Configure Locally (Optional - for testing)

Create `.env` file:
```bash
DATABASE_URL=postgres://eld_user:password@dpg-xxxxx-a.oregon-postgres.render.com/eld_trip_planner
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=your-secret-key
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
```

Load environment and migrate:
```bash
# Install python-dotenv
pip install python-dotenv

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

---

## Option 2: Railway PostgreSQL (Free $5 Credit)

### Step 1: Install Railway CLI
```bash
npm install -g @railway/cli
railway login
```

### Step 2: Create Database
```bash
cd eld-trip-planner-backend-
railway init
railway add  # Select PostgreSQL from menu
```

### Step 3: Get DATABASE_URL
```bash
railway variables  # Shows DATABASE_URL
```

Copy the URL and add to `.env`:
```
DATABASE_URL=postgresql://postgres:password@host.railway.app:5432/railway
```

### Step 4: Deploy
```bash
railway up
```

---

## Option 3: Supabase (Free 500 MB)

### Step 1: Create Project
1. Go to https://supabase.com
2. Sign up and create new project
3. Set database password (remember this!)
4. Wait 2-3 minutes for provisioning

### Step 2: Get Connection String
1. Go to **Settings** → **Database**
2. Scroll to **Connection string** → **URI**
3. Copy the connection string

Example:
```
postgresql://postgres.[project-ref]:[password]@aws-0-us-west-1.pooler.supabase.com:6543/postgres
```

### Step 3: Configure and Migrate
```bash
# Add to .env
DATABASE_URL=postgresql://postgres.[ref]:[password]@aws-0-us-west-1.pooler.supabase.com:6543/postgres

# Run migrations
python manage.py migrate
```

---

## Option 4: Neon (Serverless PostgreSQL - Free)

### Step 1: Create Database
1. Go to https://neon.tech
2. Sign up with GitHub
3. Create new project:
   - Name: `eld-trip-planner`
   - Region: US East
   - Postgres version: 16

### Step 2: Get Connection String
1. Click **Connection Details**
2. Copy **Connection string**

Example:
```
postgres://user:password@ep-xxx-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require
```

---

## Option 5: ElephantSQL (Free 20 MB - Good for Testing)

### Step 1: Create Instance
1. Go to https://www.elephantsql.com
2. Sign up and create new instance
3. Plan: **Tiny Turtle** (Free)
4. Name: `eld-trip-planner`
5. Region: Choose closest

### Step 2: Get URL
1. Click your instance
2. Copy **URL** field

Example:
```
postgres://username:password@tai.db.elephantsql.com/username
```

---

## Testing Your Database Connection

Run this command to test:
```bash
python test_database_url.py
```

Or manually test:
```python
import psycopg2
conn = psycopg2.connect("your-database-url-here")
print("✅ Connected!")
conn.close()
```

---

## Production Deployment with Database

### For Render Web Service:

1. Create PostgreSQL (as above)
2. Create **Web Service**:
   - Connect GitHub repo
   - Build Command: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
   - Start Command: `gunicorn core.wsgi:application`
3. Add Environment Variables:
   - `DATABASE_URL`: Link to your PostgreSQL instance
   - `DJANGO_SECRET_KEY`: Generate new secret
   - `DJANGO_DEBUG`: `False`
   - `DJANGO_ALLOWED_HOSTS`: `.onrender.com`

### Automatic Setup with render.yaml:

Just push to GitHub - Render reads `render.yaml` and sets everything up automatically!

---

## Environment Variables Checklist

✅ `DATABASE_URL` - From hosting provider
✅ `DJANGO_SECRET_KEY` - Generate: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
✅ `DJANGO_DEBUG` - Set to `False`
✅ `DJANGO_ALLOWED_HOSTS` - Your domain
✅ `CORS_ALLOWED_ORIGINS` - Your frontend URL

---

## Troubleshooting

**"connection refused"**: Check if your IP is whitelisted (not needed for Render/Railway)

**"SSL required"**: Add `?sslmode=require` to DATABASE_URL

**"peer authentication failed"**: Use connection string exactly as provided

**Migrations failing**: Ensure DATABASE_URL is set before running `python manage.py migrate`
