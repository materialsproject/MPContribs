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
# ConsumerSettings — the SPARSE per-consumer override.
#
# An override stores only the limits an admin explicitly set; every unset field is ``None`` and
# inherits the current global default at resolve time (``ConsumerSettings.resolve``). Nothing is
# snapshotted, so an unset limit always tracks the live global rather than freezing at creation.
# ---------------------------------------------------------------------------


class TestConsumerSettingsSparse:
    def test_unset_fields_are_none(self):
        settings = ConsumerSettings()
        assert settings.project is None
        assert settings.contribution is None
        assert settings.initiative is None

    def test_unset_leaves_within_a_set_domain_are_none(self):
        settings = ConsumerSettings(project=ConsumerProjectSettings(max_projects=99))
        assert settings.project is not None
        assert settings.project.max_projects == 99
        assert settings.project.max_columns is None  # sibling leaf left unset

    def test_only_explicit_field_is_marked_set(self):
        # update_one relies on exclude_unset (recursively flattened to settings.<domain>.<leaf>) to
        # touch only the named limit, so a partial override must report exactly the supplied leaves.
        settings = ConsumerSettings(project=ConsumerProjectSettings(max_columns=5))
        assert settings.model_dump(exclude_unset=True) == {"project": {"max_columns": 5}}

    def test_negative_limit_rejected(self):
        # Limits are counts; ``ge=0`` guards against a nonsensical negative override.
        with pytest.raises(ValueError):
            ConsumerProjectSettings(max_projects=-1)


class TestConsumerSettingsResolve:
    def test_empty_override_resolves_to_globals(self):
        resolved = ConsumerSettings().resolve(get_settings().consumer)
        assert resolved == get_settings().consumer

    def test_set_leaf_overrides_only_that_leaf(self):
        globals_ = get_settings().consumer
        resolved = ConsumerSettings(project=ConsumerProjectSettings(max_projects=1)).resolve(globals_)
        # The one set leaf wins; every sibling — in the same domain and in others — keeps the global.
        assert resolved.project.max_projects == 1
        assert resolved.project.max_columns == globals_.project.max_columns
        assert resolved.contribution.max_components == globals_.contribution.max_components

    def test_resolve_tracks_live_global(self, monkeypatch):
        # An unset leaf reads the global at resolve time, not at override-creation time.
        override = ConsumerSettings(project=ConsumerProjectSettings(max_projects=1))
        monkeypatch.setattr(get_settings().consumer.project, "max_columns", 7)
        resolved = override.resolve(get_settings().consumer)
        assert resolved.project.max_projects == 1  # explicit override preserved
        assert resolved.project.max_columns == 7  # unset leaf picks up the new global


# ---------------------------------------------------------------------------
# Consumer document construction
# ---------------------------------------------------------------------------


class TestConsumerConstruction:
    def test_with_defaults_overrides_nothing(self):
        consumer = Consumer.with_defaults("kong-123")
        assert consumer.consumer_id == "kong-123"
        # A "defaults" consumer sets no overrides at all.
        assert consumer.settings.model_dump(exclude_none=True) == {}

    def test_from_input_model_stores_empty_override_when_settings_omitted(self):
        # No supplied settings → a sparse override that changes nothing (all limits inherit globals).
        consumer = Consumer.from_input_model(ConsumerIn(consumer_id="kong-x"))
        assert consumer.consumer_id == "kong-x"
        assert consumer.settings.project is None

    def test_from_input_model_preserves_supplied_override(self):
        payload = ConsumerIn(
            consumer_id="kong-y",
            settings=ConsumerSettings(contribution=ConsumerContributionSettings(max_components=7)),
        )
        consumer = Consumer.from_input_model(payload)
        assert consumer.settings.contribution is not None
        assert consumer.settings.contribution.max_components == 7
        # Only the supplied leaf is stored; siblings stay unset (inherit at resolve time).
        assert consumer.settings.contribution.max_data_depth is None
        # Server mints its own id regardless of input.
        assert consumer.id is not None
