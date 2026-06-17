import pytest
from pydantic import SecretStr
from pydantic import ValidationError as PydanticValidationError

from mpcontribs_api.config import (
    MongoSettings,
    RedisSettings,
    Settings,
    get_settings,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REQUIRED_ENV = {
    "MPCONTRIBS_ENVIRONMENT": "dev",
    "MPCONTRIBS_MONGO__URI": "mongodb://user:pass@localhost:27017",
    "MPCONTRIBS_MONGO__DB_NAME": "mpcontribs-test",
    "MPCONTRIBS_REDIS__ADDRESS": "redis://localhost:6379",
    "MPCONTRIBS_REDIS__URL": "redis://localhost:6379/0",
    "MPCONTRIBS_MAIL_DEFAULT_SENDER": "noreply@materialsproject.org",
    "MPCONTRIBS_VERSION": "0.0.0-test",
}


def _set_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)


def _mongo(**overrides) -> MongoSettings:
    return MongoSettings(uri=SecretStr("mongodb://localhost"), db_name="db", **overrides)


# ---------------------------------------------------------------------------
# MongoSettings defaults
# ---------------------------------------------------------------------------


class TestMongoSettingsDefaults:
    def test_minimal_construction(self):
        settings = _mongo()
        assert settings.db_name == "db"
        assert settings.uri.get_secret_value() == "mongodb://localhost"

    def test_uri_is_secret(self):
        settings = _mongo()
        assert "mongodb://localhost" not in repr(settings.uri)

    def test_default_pool_sizes(self):
        settings = _mongo()
        assert settings.max_pool_size == 100
        assert settings.min_pool_size == 0

    def test_default_admin_group(self):
        assert _mongo().admin_group == "admin"

    def test_default_component_limits(self):
        settings = _mongo()
        assert settings.max_components_per_contribution == 500
        assert settings.component_insert_chunk_size == 100

    def test_invalid_datetime_conversion_raises(self):
        with pytest.raises(PydanticValidationError):
            _mongo(datetime_conversion="not-a-mode")

    def test_missing_uri_raises(self):
        with pytest.raises(PydanticValidationError):
            MongoSettings(db_name="db")


# ---------------------------------------------------------------------------
# MongoSettings._clamp_concurrency
# ---------------------------------------------------------------------------


class TestClampConcurrency:
    def test_default_not_clamped(self):
        # max_pool_size=100 -> cap 50; default max_concurrent_transactions=16 stays.
        assert _mongo().max_concurrent_transactions == 16

    def test_clamped_to_half_pool_size(self):
        settings = _mongo(max_pool_size=10, max_concurrent_transactions=16)
        assert settings.max_concurrent_transactions == 5

    def test_exactly_at_cap_not_clamped(self):
        settings = _mongo(max_pool_size=32, max_concurrent_transactions=16)
        assert settings.max_concurrent_transactions == 16

    def test_pool_size_one_clamps_to_one(self):
        settings = _mongo(max_pool_size=1, max_concurrent_transactions=16)
        assert settings.max_concurrent_transactions == 1

    def test_unbounded_pool_skips_clamping(self):
        # max_pool_size=0 means "unlimited" to PyMongo; clamping is skipped.
        settings = _mongo(max_pool_size=0, max_concurrent_transactions=999)
        assert settings.max_concurrent_transactions == 999

    def test_below_cap_unchanged(self):
        settings = _mongo(max_pool_size=10, max_concurrent_transactions=2)
        assert settings.max_concurrent_transactions == 2


# ---------------------------------------------------------------------------
# Sub-settings secrets
# ---------------------------------------------------------------------------


class TestSubSettingsSecrets:
    def test_redis_secrets_masked(self):
        redis = RedisSettings(address=SecretStr("redis://h"), url=SecretStr("redis://h/0"))
        assert redis.address.get_secret_value() == "redis://h"
        assert "redis://h" not in repr(redis)


# ---------------------------------------------------------------------------
# Settings: env var loading
# ---------------------------------------------------------------------------


class TestSettingsEnvLoading:
    def test_loads_from_env(self, monkeypatch):
        _set_required_env(monkeypatch)
        settings = Settings()
        assert settings.environment == "dev"
        assert settings.version == "0.0.0-test"
        assert settings.mail_default_sender == "noreply@materialsproject.org"

    def test_nested_delimiter_populates_mongo(self, monkeypatch):
        _set_required_env(monkeypatch)
        settings = Settings()
        assert settings.mongo.db_name == "mpcontribs-test"
        assert settings.mongo.uri.get_secret_value() == "mongodb://user:pass@localhost:27017"

    def test_nested_delimiter_populates_and_redis(self, monkeypatch):
        _set_required_env(monkeypatch)
        settings = Settings()
        assert settings.redis.url.get_secret_value() == "redis://localhost:6379/0"

    def test_nested_field_override(self, monkeypatch):
        _set_required_env(monkeypatch)
        monkeypatch.setenv("MPCONTRIBS_MONGO__MAX_POOL_SIZE", "10")
        settings = Settings()
        assert settings.mongo.max_pool_size == 10
        # Clamp validator runs on env-loaded values too.
        assert settings.mongo.max_concurrent_transactions == 5

    def test_invalid_environment_raises(self, monkeypatch):
        _set_required_env(monkeypatch)
        monkeypatch.setenv("MPCONTRIBS_ENVIRONMENT", "staging")
        with pytest.raises(PydanticValidationError):
            Settings()

    def test_missing_required_env_raises(self, monkeypatch):
        for key in REQUIRED_ENV:
            monkeypatch.delenv(key, raising=False)
        with pytest.raises(PydanticValidationError):
            Settings()


# ---------------------------------------------------------------------------
# get_settings caching
# ---------------------------------------------------------------------------


class TestGetSettingsCaching:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    def test_returns_settings_instance(self, monkeypatch):
        _set_required_env(monkeypatch)
        assert isinstance(get_settings(), Settings)

    def test_same_instance_returned(self, monkeypatch):
        _set_required_env(monkeypatch)
        assert get_settings() is get_settings()

    def test_env_changes_ignored_until_cache_cleared(self, monkeypatch):
        _set_required_env(monkeypatch)
        first = get_settings()
        monkeypatch.setenv("MPCONTRIBS_VERSION", "9.9.9")
        assert get_settings().version == first.version
        get_settings.cache_clear()
        assert get_settings().version == "9.9.9"
