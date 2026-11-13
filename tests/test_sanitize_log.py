"""tools/sanitize_log.py hides personal data but keeps device data."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "sanitize_log", Path(__file__).resolve().parents[1] / "tools" / "sanitize_log.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_masks_personal_data_keeps_device_data():
    raw = ('{"username":"mario.rossi@example.com","useruid":"18b92f88-18d5-4f11-838b-ce66e53650c3",'
           '"password":"x","token":"token-49298bee-b1d8-4498-ac0e-f97c6def585f","source":"012908FAB00699",'
           '"plantsecret":"abc","latitude":45.54,"longitude":10.21,'
           '"args":[{"idsf":9548296,"elements":[{"sfetype":"SFE_State_OnOff","value":"On"}]}]} '
           'wss://x/deviceproxy?duid=012908FAB00699&access_token=eyJhbGc.eyJzdWIi.c2ln')
    out = mod.sanitize(raw)
    for secret in ("mario.rossi", "18b92f88", "49298bee", "012908FAB00699", '"abc"', "45.54", "eyJhbGc"):
        assert secret not in out
    assert "9548296" in out and "SFE_State_OnOff" in out and '"value":"On"' in out
