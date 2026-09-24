from pathlib import Path
import json
from mod_regression.sample_inventory import inventory_samples


def test_inventory_multiple_files(tmp_path):
    (tmp_path / "a.ts").write_bytes(b"a")
    (tmp_path / "b.ts").write_bytes(b"b")

    inventory = inventory_samples(tmp_path)

    assert len(inventory) == 2
    assert all("sha256" in i for i in inventory)
