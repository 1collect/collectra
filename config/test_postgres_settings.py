"""Run tests against an isolated PostgreSQL database with fast password hashing."""
from .test_settings import *  # noqa: F403
from .settings import DATABASES as POSTGRES_DATABASES

DATABASES = POSTGRES_DATABASES
