#!/usr/bin/python

import sys
from os import path


from operator import and_

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))


from flask import Blueprint, make_response, request, redirect, url_for, g

from decorators import template_renderer
from mod_auth.controllers import login_required, check_access_rights
from mod_auth.models import Role
from mod_home.models import CCExtractorVersion, GeneralData
from mod_regression.models import Category, RegressionTest, regressionTestCategoryLinkTable
from mod_sample.forms import EditSampleForm, DeleteSampleForm, \
    DeleteAdditionalSampleForm
from mod_sample.media_info_parser import MediaInfoFetcher, \
    InvalidMediaInfoError

from mod_sample.models import Sample, ExtraFile, ForbiddenExtension
from mod_test.models import Test, TestResult, TestResultFile
from mod_upload.models import Platform
from mod_sample.media_info_parser import MediaInfoFetcher
from mod_upload.models import Upload
from database import create_session

# Need to append server root path to ensure we can import the necessary files.
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))


def run():

    db = create_session(sys.argv[1])

    #create sample database

    category = Category('Broken','Samples that are broken')
    db.add(category)
    db.commit()


    db = create_session(sys.argv[1])
    category = Category('DVB','Samples that contain DVB subtitles')
    db.add(category)
    db.commit()

    db = create_session(sys.argv[1])
    category = Category('DVD','Samples that contain DVD subtitles')
    db.add(category)
    db.commit()

    db = create_session(sys.argv[1])
    category = Category('MP4','Samples that are stored in the MP4 format')
    db.add(category)
    db.commit()

    db = create_session(sys.argv[1])
    category = Category('General','General regression samples')
    db.add(category)
    db.commit()


    db = create_session(sys.argv[1])
    sample = Sample('sample1','ts','sample1')
    db.add(sample)
    db.commit()
    MediaInfoFetcher.generate_media_xml(sample)

    db = create_session(sys.argv[1])
    sample = Sample('sample2','mpg','sample2')
    db.add(sample)
    db.commit()
    MediaInfoFetcher.generate_media_xml(sample)


    db = create_session(sys.argv[1])
    cc_version = CCExtractorVersion('0.84','2016-12-16','77da2dc873cc25dbf606a3b04172aa9fb1370f32')
    db.add(cc_version)
    db.commit()

    db = create_session(sys.argv[1])
    reg_test = RegressionTest('1','-autoprogram -out=ttxt -latin1','file','file',10)
    db.add(reg_test)
    db.commit()

    db = create_session(sys.argv[1])
    reg_test = RegressionTest('2','-autoprogram -out=ttxt -latin1 -ucla','file','file',10)
    db.add(reg_test)
    db.commit()

    db = create_session(sys.argv[1])
    gen_data = GeneralData('last_commit','71dffd6eb30c1f4b5cf800307de845072ce33262')
    db.add(gen_data)
    db.commit()


run()
