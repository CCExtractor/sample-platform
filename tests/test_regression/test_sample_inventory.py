import tempfile
from pathlib import Path
from unittest import mock
from mod_regression.sample_inventory import probe_sample


def fake_run(cmd, **kwargs):
    class R:
        returncode = 0
        stdout = (
            '{"format":{"format_name":"mpegts","duration":"10.0"},'
            '"streams":[{"codec_type":"video","codec_name":"h264"}]}'
        )
        stderr = "Detected CEA-608 captions"
    return R()


@mock.patch("mod_regression.sample_inventory.subprocess.run", side_effect=fake_run)
def test_probe_sample_basic(mock_run):
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "sample.ts"
        f.write_bytes(b"dummy")

        result = probe_sample(f)

        assert result["container"] == "mpegts"
        assert result["duration_sec"] == 10.0
        assert "CEA-608" in result["caption_types_detected"]
        assert result["streams"][0]["codec"] == "h264"
