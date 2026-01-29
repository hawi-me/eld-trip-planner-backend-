#!/usr/bin/env python
"""
Test script to verify DATABASE_URL connection.
Usage: python test_database_url.py
"""

import os
import sys

# Load .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️  python-dotenv not installed")

def test_database_url():
    """Test if DATABASE_URL is valid and can connect."""
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        print("❌ DATABASE_URL environment variable not set")
        print("\nUsing SQLite (development mode)")
        return
    
    print(f"✓ DATABASE_URL found")
    print(f"  Type: {'PostgreSQL' if 'postgres' in database_url else 'MySQL' if 'mysql' in database_url else 'Unknown'}")
    
    # Test connection
    try:
        import dj_database_url
        db_config = dj_database_url.parse(database_url)
        
        print(f"  Host: {db_config.get('HOST')}")
        print(f"  Port: {db_config.get('PORT')}")
        print(f"  Database: {db_config.get('NAME')}")
        print(f"  User: {db_config.get('USER')}")
        
        # Try actual connection
        if 'postgres' in database_url:
            try:
                import psycopg2
                conn = psycopg2.connect(database_url)
                conn.close()
                print("\n✅ PostgreSQL connection successful!")
            except ImportError:
                print("\n⚠️  psycopg2 not installed. Run: pip install psycopg2-binary")
            except Exception as e:
                print(f"\n❌ Connection failed: {e}")
        
    except Exception as e:
        print(f"\n❌ Invalid DATABASE_URL format: {e}")

if __name__ == '__main__':
    test_database_url()
