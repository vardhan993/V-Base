from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _project_root() -> Path:
    """Resolve the project root (the directory containing backend/ and apps/).

    Previous versions used bare relative paths (``Path("database")``), so the
    uploads/backups location silently depended on the process working
    directory. Anchoring to the project root keeps one canonical location no
    matter where uvicorn is launched from.
    """
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "backend").is_dir() and (parent / "apps").is_dir():
            return parent
    # Fallback for non-standard layouts: backend/src/nexus/core -> root is 4 up.
    if len(here.parents) >= 5:
        return here.parents[4]
    return Path.cwd()


_PROJECT_ROOT = _project_root()

#: Placeholder that must never reach production. ``validate_production`` refuses
#: to boot a production process that still uses it.
INSECURE_SECRET = "change-me-in-production-do-not-use-this"

#: Local development DSN. Not a secret: it points at a throwaway database on
#: loopback that developers create with ``scripts/dev-postgres``. Production and
#: staging must supply DATABASE_URL explicitly - there is no silent fallback to
#: another engine, and never to SQLite.
DEV_DATABASE_URL = "postgresql+asyncpg://vbase:vbase_dev_pw@127.0.0.1:5433/vbase"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Both files are read so the service works whether it is launched from
        # the repository root or from backend/. Real environment variables
        # always win over either file.
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "V-Base"
    app_version: str = "0.2.0"
    tagline: str = "Your Business Data. One Powerful Base."
    environment: str = "development"

    backend_host: str = "127.0.0.1"
    backend_port: int = 8000

    frontend_url: str = "http://localhost:5173"
    #: Extra browser origins allowed to call the API (comma separated). Needed
    #: when the SPA is served from a different host than the API, e.g. a
    #: Cloudflare Workers Static Assets URL.
    extra_allowed_origins: str = ""

    # ------------------------------------------------------------------
    # PostgreSQL
    # ------------------------------------------------------------------
    #: Full SQLAlchemy async DSN, e.g.
    #: postgresql+asyncpg://user:pass@host/db?sslmode=require
    database_url: str = DEV_DATABASE_URL
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout: int = 30
    #: Recycle connections before Neon/pooler idle timeouts cut them.
    db_pool_recycle: int = 600
    db_echo: bool = False
    #: Disable connection pooling entirely (NullPool). Useful when every query
    #: runs in a fresh event loop - serverless handlers and the test suite.
    db_use_null_pool: bool = False
    #: asyncpg prepared-statement cache. Forced to 0 automatically when the DSN
    #: points at a PgBouncer transaction pooler (Neon "-pooler" host, Supabase
    #: port 6543), because prepared statements cannot be reused there.
    db_statement_cache_size: int = 100
    #: Per-statement timeout in seconds, applied to every connection.
    db_command_timeout: int = 30

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------
    uploads_dir: Path = _PROJECT_ROOT / "uploads"
    backups_dir: Path = _PROJECT_ROOT / "backups"
    #: ``pg_dump``/``pg_restore`` binaries. When absent the app degrades to
    #: logical JSON snapshots instead of failing backup requests.
    pg_dump_path: str = "pg_dump"
    pg_restore_path: str = "pg_restore"

    # ------------------------------------------------------------------
    # Auth / sessions
    # ------------------------------------------------------------------
    secret_key: str = INSECURE_SECRET
    session_cookie_name: str = "vbase_session"
    session_max_age_seconds: int = 86400 * 7
    #: Send the cookie only over HTTPS. Forced on in production.
    session_cookie_secure: bool = False

    # ------------------------------------------------------------------
    # Limits
    # ------------------------------------------------------------------
    allowed_upload_extensions: tuple[str, ...] = (".csv", ".xlsx", ".xls")
    max_upload_bytes: int = 50 * 1024 * 1024
    #: Credential endpoints (login, signup, change password) - deliberately tight.
    rate_limit_auth_per_minute: int = 10
    #: Session probes such as GET /auth/me and /auth/sessions. The SPA calls these
    #: on every page load, so the ceiling has to allow normal navigation bursts.
    rate_limit_session_per_minute: int = 240
    rate_limit_write_per_minute: int = 240

    @field_validator("database_url")
    @classmethod
    def _must_be_postgres(cls, value: str) -> str:
        if not value.startswith(("postgresql", "postgres://", "postgresql+asyncpg")):
            raise ValueError(
                "DATABASE_URL must be a PostgreSQL DSN (postgresql+asyncpg://...). "
                "V-Base does not support SQLite or any other engine."
            )
        return value

    @property
    def allowed_origins(self) -> list[str]:
        origins = {
            self.frontend_url.rstrip("/"),
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        }
        for extra in self.extra_allowed_origins.split(","):
            extra = extra.strip().rstrip("/")
            if extra:
                origins.add(extra)
        return sorted(o for o in origins if o)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def cookie_secure(self) -> bool:
        return self.session_cookie_secure or self.is_production

    @property
    def uploads_path(self) -> Path:
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        return self.uploads_dir

    @property
    def backups_path(self) -> Path:
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        return self.backups_dir

    def validate_production(self) -> None:
        """Fail fast on insecure production configuration sets."""
        if not self.is_production:
            return
        problems: list[str] = []
        if self.secret_key == INSECURE_SECRET or len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be set to a random value of at least 32 characters")
        if self.database_url == DEV_DATABASE_URL:
            problems.append("DATABASE_URL must point at the managed PostgreSQL instance")
        if problems:
            raise RuntimeError("Refusing to start in production: " + "; ".join(problems))


settings = Settings()
