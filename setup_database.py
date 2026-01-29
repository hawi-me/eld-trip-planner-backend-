#!/usr/bin/env python
"""
Interactive Database Setup Script
Helps you configure a hosted database for the ELD Trip Planner backend.
"""

import os
import sys

def generate_secret_key():
    """Generate a new Django secret key."""
    try:
        from django.core.management.utils import get_random_secret_key
        return get_random_secret_key()
    except ImportError:
        import secrets
        return secrets.token_urlsafe(50)

def create_env_file():
    """Create .env file with database configuration."""
    print("🔧 ELD Trip Planner - Database Setup\n")
    print("=" * 60)
    
    # Check if .env already exists
    if os.path.exists('.env'):
        response = input("\n⚠️  .env file already exists. Overwrite? (y/n): ")
        if response.lower() != 'y':
            print("❌ Setup cancelled.")
            return
    
    print("\nSelect your database provider:\n")
    print("1. Render PostgreSQL (Recommended - Free)")
    print("2. Railway PostgreSQL")
    print("3. Supabase")
    print("4. Neon")
    print("5. ElephantSQL")
    print("6. Custom PostgreSQL URL")
    print("7. Keep SQLite (Development only)")
    
    choice = input("\nEnter choice (1-7): ").strip()
    
    env_content = []
    
    if choice == '7':
        print("\n✓ Using SQLite for development")
        env_content.append("# SQLite Development Mode")
        env_content.append("DJANGO_DEBUG=True")
        database_url = None
    else:
        print("\n" + "=" * 60)
        print("DATABASE SETUP")
        print("=" * 60)
        
        if choice == '1':
            print("\n📖 Render Setup Instructions:")
            print("1. Go to https://dashboard.render.com")
            print("2. Create New → PostgreSQL")
            print("3. Copy the 'Internal Database URL' or 'External Database URL'")
        elif choice == '2':
            print("\n📖 Railway Setup Instructions:")
            print("1. Run: railway login")
            print("2. Run: railway add (select PostgreSQL)")
            print("3. Run: railway variables (copy DATABASE_URL)")
        elif choice == '3':
            print("\n📖 Supabase Setup Instructions:")
            print("1. Go to https://supabase.com")
            print("2. Create project")
            print("3. Settings → Database → Connection string → URI")
        elif choice == '4':
            print("\n📖 Neon Setup Instructions:")
            print("1. Go to https://neon.tech")
            print("2. Create project")
            print("3. Copy connection string from dashboard")
        elif choice == '5':
            print("\n📖 ElephantSQL Setup Instructions:")
            print("1. Go to https://elephantsql.com")
            print("2. Create instance (Tiny Turtle - Free)")
            print("3. Copy URL from instance details")
        
        print("\n" + "=" * 60)
        database_url = input("\nPaste your DATABASE_URL: ").strip()
        
        if not database_url:
            print("❌ No DATABASE_URL provided. Using SQLite.")
            database_url = None
        else:
            env_content.append(f"DATABASE_URL={database_url}")
    
    # Secret key
    print("\n" + "=" * 60)
    secret_key = generate_secret_key()
    env_content.append(f"DJANGO_SECRET_KEY={secret_key}")
    print(f"✓ Generated secret key: {secret_key[:20]}...")
    
    # Debug mode
    print("\n" + "=" * 60)
    debug = input("\nEnable DEBUG mode? (y/n) [n]: ").strip().lower()
    env_content.append(f"DJANGO_DEBUG={'True' if debug == 'y' else 'False'}")
    
    # Allowed hosts
    print("\n" + "=" * 60)
    print("\nAllowed hosts (comma-separated):")
    print("Examples:")
    print("  - Development: localhost,127.0.0.1")
    print("  - Production: myapp.onrender.com,myapp.railway.app")
    allowed_hosts = input("Enter allowed hosts [localhost,127.0.0.1]: ").strip()
    if not allowed_hosts:
        allowed_hosts = "localhost,127.0.0.1"
    env_content.append(f"DJANGO_ALLOWED_HOSTS={allowed_hosts}")
    
    # CORS origins
    print("\n" + "=" * 60)
    print("\nCORS allowed origins (comma-separated):")
    print("Examples:")
    print("  - Development: http://localhost:3000,http://localhost:5173")
    print("  - Production: https://myfrontend.com")
    cors_origins = input("Enter CORS origins [http://localhost:3000]: ").strip()
    if not cors_origins:
        cors_origins = "http://localhost:3000,http://localhost:5173"
    env_content.append(f"CORS_ALLOWED_ORIGINS={cors_origins}")
    
    # Write .env file
    with open('.env', 'w') as f:
        f.write('\n'.join(env_content))
    
    print("\n" + "=" * 60)
    print("✅ .env file created successfully!")
    print("=" * 60)
    
    # Next steps
    print("\n📋 NEXT STEPS:\n")
    
    if database_url:
        print("1. Install dependencies:")
        print("   pip install python-dotenv psycopg2-binary dj-database-url")
        print("\n2. Run migrations:")
        print("   python manage.py migrate")
        print("\n3. Create superuser:")
        print("   python manage.py createsuperuser")
        print("\n4. Start server:")
        print("   python manage.py runserver")
        print("\n5. Test connection:")
        print("   python test_database_url.py")
    else:
        print("1. Using SQLite - ready to run:")
        print("   python manage.py migrate")
        print("   python manage.py runserver")
    
    print("\n" + "=" * 60)

def load_env_file():
    """Load environment variables from .env file."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ Environment variables loaded from .env")
    except ImportError:
        print("⚠️  python-dotenv not installed. Install it:")
        print("   pip install python-dotenv")

if __name__ == '__main__':
    try:
        create_env_file()
    except KeyboardInterrupt:
        print("\n\n❌ Setup cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
