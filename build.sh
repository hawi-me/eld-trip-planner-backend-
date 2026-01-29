#!/bin/bash
# build.sh - Render deployment script

set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --noinput
python manage.py migrate
