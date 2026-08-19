import pytest

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains.consumers.models import (
    Consumer,
    ConsumerIn,
    ConsumerSettings,
)

# ---------------------------------------------------------------------------
# ConsumerSettings — the effective, fully-resolved limits.
#
# Every field defaults from the env-backed global ``config.consumer`` block, so an admin can supply
# only the fields they want to change and the rest inherit the global default. This is the mechanism
# behind per-consumer overrides, so its resolution rules are worth pinning.
# ---------------------------------------------------------------------------


class TestConsumerSettingsDefaults:
    def test_unset_fields_fall_back_to_global_defaults(self):
        settings = ConsumerSettings()
        globals_ = get_settings().consumer
        assert settings.max_projects == globals_.max_projects
        assert settings.max_unapproved_contributions_per_project == globals_.max_unapproved_contributions_per_project
        assert settings.max_columns == globals_.max_columns

    def test_partial_override_keeps_other_defaults(self):
        # Overriding one limit must not disturb the siblings — they still resolve to the global.
        settings = ConsumerSettings(max_projects=99)
        assert settings.max_projects == 99
        assert settings.max_columns == get_settings().consumer.max_columns

    def test_only_explicit_field_is_marked_set(self):
        # patch_one relies on exclude_unset to touch only the named limit, so a partial
        # override must report exactly the fields the admin supplied.
        settings = ConsumerSettings(max_columns=5)
        assert settings.model_dump(exclude_unset=True) == {"max_columns": 5}

    def test_defaults_track_global_config(self, monkeypatch):
        # A ConsumerSettings built after the global default changes must reflect the new value —
        # the fallback is read at construction time, not import time.
        monkeypatch.setattr(get_settings().consumer, "max_projects", 42)
        assert ConsumerSettings().max_projects == 42

    def test_negative_limit_rejected(self):
        # Limits are counts; ``ge=0`` guards against a nonsensical negative override.
        with pytest.raises(ValueError):
            ConsumerSettings(max_projects=-1)


# ---------------------------------------------------------------------------
# Consumer document construction
# ---------------------------------------------------------------------------


class TestConsumerConstruction:
    def test_with_defaults_snapshots_global_limits(self):
        consumer = Consumer.with_defaults("kong-123")
        assert consumer.consumer_id == "kong-123"
        assert consumer.settings.max_projects == get_settings().consumer.max_projects

    def test_from_input_model_fills_defaults_when_settings_omitted(self):
        # An admin who supplies no settings gets a fully-resolved snapshot of the global defaults.
        consumer = Consumer.from_input_model(ConsumerIn(consumer_id="kong-x"))
        assert consumer.consumer_id == "kong-x"
        assert consumer.settings.max_columns == get_settings().consumer.max_columns

    def test_from_input_model_preserves_supplied_override(self):
        payload = ConsumerIn(consumer_id="kong-y", settings=ConsumerSettings(max_projects=7))
        consumer = Consumer.from_input_model(payload)
        assert consumer.settings.max_projects == 7
        # Server mints its own id regardless of input.
        assert consumer.id is not None
