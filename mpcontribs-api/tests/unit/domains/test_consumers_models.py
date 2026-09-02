import pytest

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains.consumers.models import (
    Consumer,
    ConsumerContributionSettings,
    ConsumerIn,
    ConsumerProjectSettings,
    ConsumerSettings,
)

# ---------------------------------------------------------------------------
# ConsumerSettings — the effective, fully-resolved limits.
#
# Limits are domain-grouped (project/contribution/initiative). Every leaf defaults from the env-backed
# global ``config.consumer.<domain>`` block, so an admin can supply only the fields they want to change
# and the rest inherit the global default. This is the mechanism behind per-consumer overrides, so its
# resolution rules are worth pinning.
# ---------------------------------------------------------------------------


class TestConsumerSettingsDefaults:
    def test_unset_fields_fall_back_to_global_defaults(self):
        settings = ConsumerSettings()
        globals_ = get_settings().consumer
        assert settings.project.max_projects == globals_.project.max_projects
        assert settings.project.max_columns == globals_.project.max_columns
        assert settings.contribution.max_per_unapproved_project == globals_.contribution.max_per_unapproved_project
        assert settings.contribution.max_components == globals_.contribution.max_components
        assert settings.contribution.max_data_depth == globals_.contribution.max_data_depth
        assert settings.initiative.max_unapproved_per_owner == globals_.initiative.max_unapproved_per_owner
        assert settings.initiative.max_projects_per_unapproved == globals_.initiative.max_projects_per_unapproved

    def test_partial_override_keeps_other_defaults(self):
        # Overriding one limit must not disturb the siblings — they still resolve to the global.
        settings = ConsumerSettings(project=ConsumerProjectSettings(max_projects=99))
        assert settings.project.max_projects == 99
        assert settings.project.max_columns == get_settings().consumer.project.max_columns
        # A sibling domain left unset resolves to its own global defaults.
        assert settings.contribution.max_components == get_settings().consumer.contribution.max_components

    def test_only_explicit_field_is_marked_set(self):
        # update_one relies on exclude_unset (recursively flattened to settings.<domain>.<leaf>) to
        # touch only the named limit, so a partial override must report exactly the supplied leaves.
        settings = ConsumerSettings(project=ConsumerProjectSettings(max_columns=5))
        assert settings.model_dump(exclude_unset=True) == {"project": {"max_columns": 5}}

    def test_defaults_track_global_config(self, monkeypatch):
        # A ConsumerSettings built after the global default changes must reflect the new value —
        # the fallback is read at construction time, not import time.
        monkeypatch.setattr(get_settings().consumer.project, "max_projects", 42)
        assert ConsumerSettings().project.max_projects == 42

    def test_negative_limit_rejected(self):
        # Limits are counts; ``ge=0`` guards against a nonsensical negative override.
        with pytest.raises(ValueError):
            ConsumerProjectSettings(max_projects=-1)


# ---------------------------------------------------------------------------
# Consumer document construction
# ---------------------------------------------------------------------------


class TestConsumerConstruction:
    def test_with_defaults_snapshots_global_limits(self):
        consumer = Consumer.with_defaults("kong-123")
        assert consumer.consumer_id == "kong-123"
        assert consumer.settings.project.max_projects == get_settings().consumer.project.max_projects

    def test_from_input_model_fills_defaults_when_settings_omitted(self):
        # An admin who supplies no settings gets a fully-resolved snapshot of the global defaults.
        consumer = Consumer.from_input_model(ConsumerIn(consumer_id="kong-x"))
        assert consumer.consumer_id == "kong-x"
        assert consumer.settings.project.max_columns == get_settings().consumer.project.max_columns

    def test_from_input_model_preserves_supplied_override(self):
        payload = ConsumerIn(
            consumer_id="kong-y",
            settings=ConsumerSettings(contribution=ConsumerContributionSettings(max_components=7)),
        )
        consumer = Consumer.from_input_model(payload)
        assert consumer.settings.contribution.max_components == 7
        # Server mints its own id regardless of input.
        assert consumer.id is not None
