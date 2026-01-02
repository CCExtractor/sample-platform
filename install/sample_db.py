#!/usr/bin/python

import sys
from os import path

from sqlalchemy.exc import IntegrityError

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))


def run():
    from database import create_session
    from mod_auth.models import User
    from mod_customized.models import CustomizedTest
    from mod_home.models import CCExtractorVersion, GeneralData
    from mod_regression.models import (Category, InputType, OutputType,
                                       RegressionTest, RegressionTestOutput)
    from mod_sample.models import Sample
    from mod_test.models import Test
    from mod_upload.models import Upload

    db = create_session(sys.argv[1])

    entries = []
    categories = [
        Category('Broken', 'Samples that are broken'),
        Category('DVB', 'Samples that contain DVB subtitles'),
        Category('DVD', 'Samples that contain DVD subtitles'),
        Category('MP4', 'Samples that are stored in the MP4 format'),
        Category('General', 'General regression samples')
    ]
    entries.extend(categories)

    samples = [
        Sample('sample1', 'ts', 'sample1'),
        Sample('sample2', 'ts', 'sample2')
    ]
    entries.extend(samples)

    cc_version = CCExtractorVersion('0.84', '2016-12-16T00:00:00Z', '77da2dc873cc25dbf606a3b04172aa9fb1370f32')
    entries.append(cc_version)

    regression_tests = [
        RegressionTest(1, '-autoprogram -out=ttxt -latin1', InputType.file, OutputType.file, 3, 10),
        RegressionTest(2, '-autoprogram -out=ttxt -latin1 -ucla', InputType.file, OutputType.file, 1, 10),
        RegressionTest(1, '-out=webvtt', InputType.file, OutputType.file, 5, 0, True,
                       'Validates WebVTT output format compliance')
    ]
    entries.extend(regression_tests)

    gen_data = GeneralData('last_commit', '71dffd6eb30c1f4b5cf800307de845072ce33262')
    entries.append(gen_data)

    regression_test_output = [
        RegressionTestOutput(1, "test1", ".srt", "test1.srt"),
        RegressionTestOutput(2, "test2", ".srt", "test2.srt"),
        RegressionTestOutput(3, "WEBVTT\n", ".webvtt", "sample1.webvtt")
    ]
    entries.extend(regression_test_output)

    for entry in entries:
        try:
            db.add(entry)
            db.commit()
        except IntegrityError:
            print("Entry already exists!", entry, flush=True)
            db.rollback()


run()
