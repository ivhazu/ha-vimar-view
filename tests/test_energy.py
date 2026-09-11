from custom_components.vimar_cloud.energy import integrate_power_delta_kwh


def test_one_kw_for_one_hour():
    assert integrate_power_delta_kwh(1000, 1000, 3600, 7200) == 1.0


def test_trapezoid():
    assert integrate_power_delta_kwh(1000, 0, 1800, 3600) == 0.25


def test_long_gap_is_not_integrated():
    assert integrate_power_delta_kwh(1000, 1000, 301, 300) == 0.0


def test_invalid_power_is_not_integrated():
    assert integrate_power_delta_kwh(-1, 1000, 60, 300) == 0.0
    assert integrate_power_delta_kwh(1000, float("nan"), 60, 300) == 0.0
