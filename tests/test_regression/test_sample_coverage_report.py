from scripts.sample_coverage_report import build_coverage


def test_build_coverage_basic():
    inventory = [
        {"container": "mpegts", "caption_types_detected": ["CEA-608"]},
        {"container": "mpegts", "caption_types_detected": ["CEA-708"]},
        {"container": "matroska", "caption_types_detected": []},
        {"container": None, "caption_types_detected": None},
    ]

    report = build_coverage(inventory)

    assert report["total_samples"] == 4
    assert report["containers"]["mpegts"] == 2
    assert report["containers"]["matroska"] == 1
    assert report["containers"]["unknown"] == 1

    assert report["captions"]["CEA-608"] == 1
    assert report["captions"]["CEA-708"] == 1
    assert report["captions"]["none"] == 2

    assert report["matrix"]["mpegts"]["CEA-608"] == 1
    assert report["matrix"]["mpegts"]["CEA-708"] == 1
    assert report["matrix"]["matroska"]["none"] == 1
    assert report["matrix"]["unknown"]["none"] == 1
