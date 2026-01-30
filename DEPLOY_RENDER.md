# Deploy to Render - Step by Step Guide

## Prerequisites
✅ Git repository initialized
✅ GitHub account
✅ Render account (free at render.com)

---

## Step 1: Push Code to GitHub

```bash
# Add all files
git add .

# Commit changes
git commit -m "Production ready - Added comprehensive API with PostgreSQL support"

# Push to GitHub
git push origin main
```

**Important:** Make sure `.env` is in `.gitignore` (it already is) to keep your passwords safe!

---

## Step 2: Sign Up for Render

1. Go to https://dashboard.render.com
2. Click **"Get Started for Free"**
3. Sign up with GitHub (recommended - easier deployment)
4. Authorize Render to access your GitHub

---

## Step 3: Deploy Using Blueprint (Automatic Setup)

### Option A: Using render.yaml (Easiest - Everything Automatic)

1. In Render Dashboard, click **"New +"** → **"Blueprint"**
2. Connect your GitHub repository: `eld-trip-planner-backend-`
3. Render will detect `render.yaml` and show:
   - ✅ PostgreSQL Database (eld-trip-planner-db)
   - ✅ Web Service (eld-trip-planner-api)
4. Click **"Apply"**
5. Render will:
   - Create PostgreSQL database (free 256MB)
   - Set DATABASE_URL automatically
   - Build and deploy your API
   - Run migrations automatically

**Done! Your API will be live at: `https://eld-trip-planner-api.onrender.com`**

---

## Step 4: Manual Setup (If Blueprint Doesn't Work)

### 4A: Create PostgreSQL Database

1. Click **"New +"** → **"PostgreSQL"**
2. Fill in:
   - **Name**: `eld-trip-planner-db`
   - **Database**: `eld_trip_planner`
   - **User**: `eld_user`
   - **Region**: Oregon (US West)
   - **Plan**: **Free**
3. Click **"Create Database"**
4. Wait 2-3 minutes for provisioning
5. **Copy the Internal Database URL** (starts with `postgres://`)

### 4B: Create Web Service

1. Click **"New +"** → **"Web Service"**
2. Connect your GitHub repository
3. Fill in settings:
   - **Name**: `eld-trip-planner-api`
   - **Region**: Oregon (US West)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: 
     ```
     pip install -r requirements.txt && python manage.py collectstatic --noinput
     ```
   - **Start Command**: 
     ```
     gunicorn core.wsgi:application
     ```
   - **Plan**: **Free**

4. Click **"Advanced"** and add Environment Variables:

| Key | Value |
|-----|-------|
| `DJANGO_SECRET_KEY` | Click "Generate" or paste from `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_ALLOWED_HOSTS` | `.onrender.com` |
| `DATABASE_URL` | Link to your PostgreSQL instance (or paste the URL) |
| `CORS_ALLOWED_ORIGINS` | `https://your-frontend-domain.com` (or leave default) |
| `PYTHON_VERSION` | `3.12.0` |

5. Click **"Create Web Service"**

---

## Step 5: Monitor Deployment

1. Watch the build logs in Render dashboard
2. Look for:
   ```
   Building...
   ✓ pip install -r requirements.txt
   ✓ python manage.py collectstatic
   ✓ Starting gunicorn
   ==> Your service is live 🎉
   ```

3. First deploy takes ~5-10 minutes

---

## Step 6: Run Initial Migrations

After deployment, open the **Shell** tab in your web service:

```bash
python manage.py migrate
python manage.py createsuperuser
```

Or use the build command with migrations (already in render.yaml):
```yaml
buildCommand: pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate
```

---

## Step 7: Test Your Deployed API

Your API endpoints will be available at:

```
https://eld-trip-planner-api.onrender.com/api/
https://eld-trip-planner-api.onrender.com/api/health/
https://eld-trip-planner-api.onrender.com/api/trips/
https://eld-trip-planner-api.onrender.com/admin/
```

**Test with curl or browser:**
```bash
curl https://eld-trip-planner-api.onrender.com/api/health/
```

---

## Step 8: Configure Frontend CORS

Update your environment variable:
```
CORS_ALLOWED_ORIGINS=https://your-frontend-app.vercel.app,https://your-frontend-app.netlify.app
```

Go to your web service → Environment tab → Add the frontend URL

---

## Troubleshooting

### Build Failed
- Check logs for missing dependencies
- Verify `requirements.txt` is complete
- Check Python version in `runtime.txt`

### Database Connection Error
- Verify DATABASE_URL is set correctly
- Check if PostgreSQL database is running
- Ensure Internal Database URL is used (not External)

### Static Files Not Loading
- Verify `collectstatic` runs in build command
- Check STATIC_ROOT setting
- Ensure WhiteNoise is installed

### CORS Errors
- Add frontend URL to CORS_ALLOWED_ORIGINS
- Check if `.onrender.com` is in ALLOWED_HOSTS

---

## Free Tier Limits

**Render Free Tier:**
- ✅ 750 hours/month web service uptime
- ✅ 256MB PostgreSQL database
- ✅ Automatic SSL certificates
- ✅ Auto-deploy on git push
- ⚠️ Sleeps after 15 min inactivity (wakes on request in ~30 sec)
- ⚠️ Build time: 10 minutes max

**Upgrade if you need:**
- Faster performance
- No sleep/downtime
- More database storage
- Faster builds

---

## Automatic Deployments

Render auto-deploys when you push to GitHub:

```bash
# Make changes
git add .
git commit -m "Update feature"
git push origin main

# Render automatically:
# 1. Detects push
# 2. Pulls code
# 3. Runs build command
# 4. Deploys new version
# 5. Runs health checks
```

---

## Your API is Now Live! 🚀

**Production URL:** `https://eld-trip-planner-api.onrender.com`

**Next Steps:**
1. Update frontend to use production API URL
2. Test all endpoints
3. Monitor logs for errors
4. Set up custom domain (optional)

---

## Environment Variables Summary

Required for production:

```env
DATABASE_URL=postgres://...  (auto-set by Render)
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=.onrender.com
CORS_ALLOWED_ORIGINS=https://your-frontend.com
PYTHON_VERSION=3.12.0
```

---

## Need Help?

- Render Docs: https://render.com/docs
- Django Deployment: https://docs.djangoproject.com/en/4.2/howto/deployment/
- Your render.yaml: Already configured in project root
