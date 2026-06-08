from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RedisSettings(BaseModel):
    address: SecretStr
    url: SecretStr


class KongSettings(BaseModel):
    gateway_secret: SecretStr


class MongoSettings(BaseModel):
    """MongoDB settings.

    Provided defaults are the defaults of AsyncMongoClient
    """

    uri: SecretStr = Field(description="The full uri from MongoDB (username and password included)")
    db_name: str
    max_pool_size: int = Field(
        default=100,
        description="Maximum number of allowed concurrent connection to each server. Can be '0' or 'None', both of "
        "which allow any number of connections",
    )
    min_pool_size: int = Field(
        default=0,
        description="Minimum number of concurent connections that the pool will maintain connected to each server ",
    )
    datetime_conversion: Literal["datetime_ms", "datetime", "datetime_auto", "datetime_clamp"] = Field(
        default="datetime",
        description="Specifies how UTC datetimes should be decoded within BSON",
    )
    server_selection_timeout_ms: int = Field(
        default=30000,
        description="Controls how long (in milliseconds) the driver will wait to find an available, appropriate server "
        "to carry out a database operation;"
        "while it is waiting, multiple server monitoring operations may be carried out",
    )

    admin_group: str = Field(
        default="admin",
        description="Name of admin group to consider in requests to MongoDB. Not directly passed to Mongo, but "
        "consumed by auth.",
    )

    # TODO: Tune default
    max_concurrent_transactions: int = Field(
        default=16,
        description="Upper bound on per-contribution transactions running in parallel during a bulk insert. Clamped at "
        "construction to max_pool_size // 2 so reads on the same request can still acquire connections.",
    )
    # TODO: Tune default
    max_components_per_contribution: int = Field(
        default=500,
        description="Hard ceiling on structures + tables + attachments for a single contribution. Anything larger is "
        "rejected upfront so we don't burn a transaction slot on a request guaranteed to exceed "
        "transactionLifetimeLimitSeconds (default 60s).",
    )
    # TODO: Tune default
    component_insert_chunk_size: int = Field(
        default=100,
        description="Batch size used by component repositories when chunking insert_many calls inside a transaction.",
    )

    @model_validator(mode="after")
    def _clamp_concurrency(self):
        if self.max_pool_size:
            per_request_cap = max(1, self.max_pool_size // 2)
            if self.max_concurrent_transactions > per_request_cap:
                self.max_concurrent_transactions = per_request_cap
            global_cap = max(1, self.max_pool_size - 10)
            if self.max_global_concurrent_writes > global_cap:
                self.max_global_concurrent_writes = global_cap
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        env_prefix="MPCONTRIBS_",
    )

    environment: Literal["dev", "prod"]

    mongo: MongoSettings

    kong: KongSettings

    redis: RedisSettings

    # SMTP Settings
    mail_default_sender: str = Field(
        description="SMTP Server to send out notifications on new projects and other important moments"
    )

    # General/Informative settings
    version: str


@lru_cache
def get_settings() -> Settings:
    # Fields are populated from env vars at runtime, not from arguments - pyright can't see that
    return Settings()  # pyright: ignore[reportCallIssue]
