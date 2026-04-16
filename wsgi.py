"""WSGI entry point.

Used by:
- gunicorn in production (`gunicorn wsgi:app`)
- `flask --app wsgi run` if you prefer to be explicit
- `python wsgi.py` for a direct dev run

For dev you can also run `flask --app app run` — Flask auto-discovers the
`create_app()` factory inside the `app` package.
"""

from __future__ import annotations

from app import create_app

app = create_app()


if __name__ == "__main__":
    import os

    app.run(debug=os.environ.get("FLASK_ENV") == "development")
