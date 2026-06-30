"""The rendered supervisord config must export the env vars the new pydantic Settings require.

The FastAPI rewrite reads nested settings via the ``MPCONTRIBS_<group>__<field>`` convention. This
guards against regressing the supervisord template back to the Flask-era flat names, which would
make the container fail Settings validation at startup.
"""

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

SUPERVISORD_DIR = Path(__file__).resolve().parents[2] / "supervisord"

# Names the new Settings model needs present in the process environment.
REQUIRED_ENV_NAMES = [
    "MPCONTRIBS_ENVIRONMENT",
    "MPCONTRIBS_MAIL_DEFAULT_SENDER",
    "MPCONTRIBS_VERSION",
    "MPCONTRIBS_OTEL__OTLP_ENDPOINT",
]


def _render() -> str:
    env = Environment(loader=FileSystemLoader(str(SUPERVISORD_DIR)))
    template = env.get_template("supervisord.conf.jinja")
    return template.render(
        production=True,
        environment="prod",
        version="1.2.3",
        deployments={
            "ml": {
                "api_port": "10002",
                "portal_port": 8082,
                "db": "ml",
                "s3": "ml",
                "tm": "MP",
                "max_projects": 3,
            }
        },
        nworkers=2,
        reload=0,
        node_env="production",
        flask_debug=False,
        flask_log_level="INFO",
        jupyter_gateway_url="http://localhost:10100",
        jupyter_gateway_host="localhost:10100",
        otel_endpoint="localhost:4317",
        mpcontribs_api_host="localhost",
    )


@pytest.mark.parametrize("name", REQUIRED_ENV_NAMES)
def test_required_env_name_present(name: str) -> None:
    assert name in _render()


def test_no_stale_flat_mongo_db_name() -> None:
    rendered = _render()
    # The old flat name must not appear as an assignment (the nested name is required instead).
    assert "MPCONTRIBS_DB_NAME=" not in rendered
