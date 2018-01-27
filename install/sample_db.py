#!/usr/bin/python
"""
Sample Database to initialize the first build with
===================
This script creates an instance of a database.
"""


import sys
from os import path

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))


def run():
    from mod_home.models import CCExtractorVersion, GeneralData
    from mod_regression.models import Category, RegressionTest, InputType, OutputType
    from mod_sample.models import Sample
    from mod_upload.models import Upload
    from mod_auth.models import User
    from database import create_session

    db = create_session(sys.argv[1])
    """
    Create a database session and add the test categories
    """
    categories = [
        Category('Broken', 'Samples that are broken'),
        Category('DVB', 'Samples that contain DVB subtitles'),
        Category('DVD', 'Samples that contain DVD subtitles'),
        Category('MP4', 'Samples that are stored in the MP4 format'),
        Category('General', 'General regression samples')
    ]
    db.add_all(categories)
    db.commit()

    samples = [
        Sample('sample1', 'ts', 'sample1'),
        Sample('sample2', 'ts', 'sample2')
    ]
    db.add_all(samples)
    db.commit()

    cc_version = CCExtractorVersion('0.84', '2016-12-16', '77da2dc873cc25dbf606a3b04172aa9fb1370f32')
    db.add(cc_version)
    db.commit()

    """
    Perform regression tests on the created database instanse
    """
    regression_tests = [
        RegressionTest(1, '-autoprogram -out=ttxt -latin1', InputType.file, OutputType.file, 3, 10),
        RegressionTest(2, '-autoprogram -out=ttxt -latin1 -ucla', InputType.file, OutputType.file, 1, 10)
    ]
    db.add_all(regression_tests)
    db.commit()

    gen_data = GeneralData('last_commit', '71dffd6eb30c1f4b5cf800307de845072ce33262')
    db.add(gen_data)
    db.commit()


run()
