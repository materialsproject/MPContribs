from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class UserSettings(BaseModel):
    max_projects: int = Field(
        default=3,
        description="The maximum number of projects a single user is allowed to create",
    )
    max_unapproved_contributions_per_project: int = Field(
        default=500,
        description="The maximum number of unapproved contributions a single user is allowed to have per project",
    )
    max_columns: int = Field(
        default=160,
        description="The maximum number of columns a project is allowed to have",
    )


class RedisSettings(BaseModel):
    address: SecretStr
    url: SecretStr


class ObservabilitySettings(BaseModel):
    """OpenTelemetry settings.

    The application is vendor-neutral: it emits traces, metrics, and logs via OTLP/gRPC to a
    collector (in our deployment, the Datadog Agent's OTLP receiver). Datadog is purely the backend.
    """

    enabled: bool = Field(
        default=True,
        description="Master switch for OTEL setup. Disable in tests/local runs without a collector.",
    )
    service_name: str = Field(
        default="contribs-apis",
        description="Value of the service.name resource attribute. Kept as the legacy Datadog "
        "service name so existing dashboards and monitors keep resolving.",
    )
    otlp_endpoint: str = Field(
        default="localhost:4317",
        description="host:port of the OTLP/gRPC receiver (the Datadog Agent's OTLP endpoint).",
    )
    insecure: bool = Field(
        default=True,
        description="Use an insecure (plaintext) gRPC channel. True for a local/sidecar agent without TLS.",
    )
    metric_export_interval_ms: int = Field(
        default=60_000,
        description="How often (ms) the periodic metric reader exports to the collector.",
    )


class AwsSettings(BaseModel):
    """AWS Settings

    Primarily used for S3 access
    """

    region: str = Field(default="us-east-1", description="The region to connect to")
    max_pool_connections: int = Field(
        default=10,
        description="The maximum number of connections the app is allowed to have to S3",
    )
    health_bucket: str = Field(
        default="contributions",
        description="The S3 bucket probed by the healthcheck to verify connectivity",
    )


class MongoSettings(BaseModel):
    """MongoDB settings.

    Provided defaults are the defaults of AsyncMongoClient
    """

    # Required
    uri: SecretStr = Field(description="The full uri from MongoDB (username and password included)")
    db_name: str

    # Optional
    app_name: str = Field(
        default="MPContribs_FastAPI_Server",
        description="The name of the application that created this AsyncMongoClient instance. The server will log this "
        "value upon establishing each connection. It is also recorded in the slow query log and profile collections.",
    )
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
        default=30_000,
        description="Controls how long (in milliseconds) the driver will wait to find an available, appropriate server "
        "to carry out a database operation;"
        "while it is waiting, multiple server monitoring operations may be carried out",
    )

    admin_group: str = Field(
        default="admin",
        description="Name of admin group to consider in requests to MongoDB. Not directly passed to Mongo, but "
        "consumed by auth.",
    )

    compressors: str = Field(
        default="snappy,zstd,zlib",
        description="Comma separated list of compressors for wire protocol compression. Compression support must also "
        "be enabled on the server",
    )

    read_preference: str = Field(
        default="primary",
        description="The replica set read preference for this client. One of primary, primaryPreferred, secondary, "
        "secondaryPreferred, or nearest",
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
    # TODO: Tune default
    max_request_bytes: int = Field(
        default=16 * 1024 * 1024,
        description="Hard ceiling on the size (bytes) of any single request body. Requests exceeding it are rejected "
        "with 413 before the body is read into memory, so one caller can't OOM the worker. Mirrors the client's "
        "MAX_PAYLOAD (15MB) with headroom.",
    )
    # TODO: Tune default
    bulk_write_limit: int = Field(
        default=1000,
        description="Maximum number of items accepted in a single bulk contribution POST/PUT. Larger batches are "
        "rejected with 422; callers should chunk (or use the async ingestion endpoint). Advertised via GET /limits.",
    )
    max_idle_time_ms: int = Field(
        default=30_000,
        description="The maximum allowed time a single connection is allowed to sit idle",
    )
    timeout_ms: int = Field(default=60_000, description="The end-to-end allowed time for an operation")

    @model_validator(mode="after")
    def _clamp_concurrency(self):
        if self.max_pool_size:
            per_request_cap = max(1, self.max_pool_size // 2)
            if self.max_concurrent_transactions > per_request_cap:
                self.max_concurrent_transactions = per_request_cap
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        env_prefix="MPCONTRIBS_",
    )

    environment: Literal["dev", "prod"]

    # MPContribs_mongo__*
    # requires uri and db_name
    mongo: MongoSettings

    # MPContribs_aws__*
    aws: AwsSettings = Field(default_factory=AwsSettings)

    # MPContribs_redis__*
    redis: RedisSettings

    # MPContribs_otel__*
    otel: ObservabilitySettings = Field(default_factory=ObservabilitySettings)

    # MPContribs_user__*
    user: UserSettings = Field(default_factory=UserSettings)

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
