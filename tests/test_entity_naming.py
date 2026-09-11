"""Regression tests for Vimar entity naming conventions."""


def compose_entity_id(domain: str, device_name: str, entity_name: str | None) -> str:
    """Model Home Assistant's has_entity_name=True naming rule for tests."""
    slug = device_name.lower().replace(" ", "_")
    if entity_name is None:
        return f"{domain}.{slug}"
    return f"{domain}.{slug}_{entity_name.lower().replace(' ', '_')}"


def test_main_light_does_not_duplicate_device_name() -> None:
    assert compose_entity_id("light", "Faretti", None) == "light.faretti"


def test_named_secondary_entity_keeps_entity_name() -> None:
    assert compose_entity_id("sensor", "Faretti", "Potenza") == "sensor.faretti_potenza"


def test_scene_main_button_does_not_duplicate_device_name() -> None:
    assert compose_entity_id("button", "Scenario Buonanotte", None) == "button.scenario_buonanotte"
