"""Logic to fetch sample information, uploading, editing, deleting sample."""

import json
import os
from operator import and_
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

import requests
from flask import Blueprint, g, make_response, redirect, request, url_for

from decorators import template_renderer
from exceptions import SampleNotFoundException
from mod_auth.controllers import check_access_rights, login_required
from mod_auth.models import Role
from mod_home.models import CCExtractorVersion, GeneralData
from mod_regression.models import RegressionTest
from mod_sample.forms import (DeleteAdditionalSampleForm, DeleteSampleForm,
                              EditSampleForm)
from mod_sample.media_info_parser import (InvalidMediaInfoError,
                                          MediaInfoFetcher)
from mod_sample.models import ExtraFile, ForbiddenExtension, Issue, Sample
from mod_test.models import Test, TestResult, TestResultFile
from mod_upload.models import Platform
from utility import serve_file_download

mod_sample = Blueprint('sample', __name__)


@mod_sample.before_app_request
def before_app_request() -> None:
    """Curate menu items before app request."""
    g.menu_entries['samples'] = {
        'title': 'Sample info',
        'icon': 'object-group',
        'route': 'sample.index'
    }


def display_sample_info(sample) -> Dict[str, Any]:
    """
    Fetch the media info.

    :param sample: sample entry from the database
    :type sample: Model Sample
    :return: sample information if successful
    :rtype: dict
    """
    try:
        media_info_fetcher = MediaInfoFetcher(sample)
        media_info = media_info_fetcher.get_media_info()
    except InvalidMediaInfoError:
        # Try to regenerate the file
        try:
            media_info_fetcher = MediaInfoFetcher.generate_media_xml(sample)
            media_info = media_info_fetcher.get_media_info()
        except InvalidMediaInfoError:
            # in case no media info present in the sample
            media_info = None

    latest_commit = GeneralData.query.filter(GeneralData.key == 'last_commit').first().value
    last_release = CCExtractorVersion.query.order_by(CCExtractorVersion.released.desc()).first().commit

    test_commit = Test.query.filter(Test.commit == latest_commit).first()
    test_release = Test.query.filter(Test.commit == last_release).first()
    regression_tests = RegressionTest.query.filter(RegressionTest.sample_id == sample.id).all()
    status = 'Unknown'
    status_release = 'Unknown'

    if len(regression_tests) > 0:
        if test_commit is not None:
            sq = g.db.query(RegressionTest.id).filter(RegressionTest.sample_id == sample.id).subquery()
            exit_code = g.db.query(TestResult.exit_code).filter(and_(
                TestResult.exit_code != TestResult.expected_rc,
                and_(TestResult.test_id == test_commit.id, TestResult.regression_test_id.in_(sq))
            )).first()
            not_null = g.db.query(TestResultFile.got).filter(and_(
                TestResultFile.got.isnot(None),
                and_(TestResultFile.test_id == test_commit.id, TestResultFile.regression_test_id.in_(sq))
            )).first()

            if exit_code is None and not_null is None:
                status = 'Pass'
            else:
                status = 'Fail'

        if test_release is not None:
            sq = g.db.query(RegressionTest.id).filter(
                RegressionTest.sample_id == sample.id).subquery()
            exit_code = g.db.query(TestResult.exit_code).filter(
                and_(
                    TestResult.exit_code != TestResult.expected_rc,
                    and_(TestResult.test_id == test_release.id, TestResult.regression_test_id.in_(sq))
                )
            ).first()
            not_null = g.db.query(TestResultFile.got).filter(and_(
                TestResultFile.got.isnot(None),
                and_(TestResultFile.test_id == test_release.id, TestResultFile.regression_test_id.in_(sq))
            )).first()

            if exit_code is None and not_null is None:
                status_release = 'Pass'
            else:
                status_release = 'Fail'
    else:
        status = 'Not present in regression tests'
        status_release = 'Not present in regression tests'

    return {
        'sample': sample,
        'media': media_info,
        'additional_files': ExtraFile.query.filter(
            ExtraFile.sample_id == sample.id).all(),
        'latest_commit': status,
        'latest_commit_test': test_commit,
        'latest_release': status_release,
        'latest_release_test': test_release,
        'issues': Issue.query.filter(Issue.sample_id == sample.id).all()
    }


@mod_sample.errorhandler(SampleNotFoundException)
@template_renderer('sample/sample_not_found.html', 404)
def not_found(error):
    """Display sample not found page."""
    return {
        'message': error.message
    }


@mod_sample.route('/')
@template_renderer()
def index():
    """Fetch all samples and display sample's index page."""
    return {
        'samples': Sample.query.all()
    }


@mod_sample.route('/<regex("[0-9]+"):sample_id>')
@template_renderer('sample/sample_info.html')
def sample_by_id(sample_id):
    """
    Fetch sample information and display page.

    :param sample_id: id of the sample
    :type sample_id: int
    :raises SampleNotFoundException: when sample id is not found
    :return: sample information if successful
    :rtype: dict
    """
    sample = Sample.query.filter(Sample.id == sample_id).first()
    if sample is not None:
        return display_sample_info(sample)

    raise SampleNotFoundException(f"Sample with id {sample_id} not found.")


@mod_sample.route('/<regex("[A-Za-z0-9]+"):sample_hash>')
@template_renderer('sample/sample_info.html')
def sample_by_hash(sample_hash):
    """
    Fetch sample by hash.

    :param sample_hash: hash of the sample
    :type sample_hash: str
    :raises SampleNotFoundException: when sample hash is incorrect
    :return: sample info if successful
    :rtype: dict
    """
    sample = Sample.query.filter(Sample.sha == sample_hash).first()
    if sample is not None:
        return display_sample_info(sample)

    raise SampleNotFoundException(f"Sample with hash {sample_hash} not found.")


@mod_sample.route('/download/<sample_id>')
def download_sample(sample_id):
    """
    Download sample file.

    :param sample_id: id of the sample file
    :type sample_id: int
    :raises SampleNotFoundException: when sample id is not found
    :return: sample file
    :rtype: Flask response
    """
    sample = Sample.query.filter(Sample.id == sample_id).first()
    if sample is not None:
        return serve_file_download(sample.filename, 'TestFiles')
    raise SampleNotFoundException('Sample not found')


@mod_sample.route('/download/<sample_id>/media-info')
def download_sample_media_info(sample_id):
    """
    Download sample file's media information as XML.

    :param sample_id: id of the sample file
    :type sample_id: int
    :raises SampleNotFoundException: when sample id is not found
    :return: sample file's media info file
    :rtype: Flask response
    """
    from run import config
    sample = Sample.query.filter(Sample.id == sample_id).first()

    if sample is not None:
        # Fetch media info
        media_info_path = os.path.join(
            config.get('SAMPLE_REPOSITORY', ''), 'TestFiles', 'media', sample.sha + '.xml')
        if os.path.isfile(media_info_path):
            return serve_file_download(sample.sha + '.xml', 'TestFiles', 'media')

        raise SampleNotFoundException(f"Media information for sample {sample.id} not found")

    raise SampleNotFoundException(f"Sample with id {sample_id} not found")


@mod_sample.route('/download/<sample_id>/additional/<additional_id>')
def download_sample_additional(sample_id, additional_id):
    """
    Download sample file's additional files and information.

    :param sample_id: id of the sample
    :type sample_id: int
    :param additional_id: id of the additional file
    :type additional_id: int
    :raises SampleNotFoundException: when additional file id is not found
    :raises SampleNotFoundException: when sample id is not found
    :return: sample's additional information file
    :rtype: Flask response
    """
    sample = Sample.query.filter(Sample.id == sample_id).first()
    if sample is not None:
        extra = ExtraFile.query.filter(ExtraFile.id == additional_id).first()
        if extra is not None:
            return serve_file_download(extra.filename, 'TestFiles', 'extra')
        raise SampleNotFoundException(f"Extra file {additional_id} for sample {sample.id} not found")
    raise SampleNotFoundException(f"Sample with id {sample_id} not found")


@mod_sample.route('/edit/<sample_id>', methods=['GET', 'POST'])
@login_required
@check_access_rights([Role.admin])
@template_renderer()
def edit_sample(sample_id):
    """
    Edit sample, required admin role.

    :param sample_id: id of the sample
    :type sample_id: int
    :raises SampleNotFoundException: when sample id is not found
    :return: form to edit sample
    :rtype: dict
    """
    sample = Sample.query.filter(Sample.id == sample_id).first()

    if sample is not None:
        versions = CCExtractorVersion.query.all()
        # Process or render form
        form = EditSampleForm(request.form)
        form.version.choices = [(v.id, v.version) for v in versions]

        if form.validate_on_submit():
            # Store values
            upload = sample.upload
            upload.notes = form.notes.data
            upload.version_id = form.version.data
            upload.platform = Platform.from_string(form.platform.data)
            upload.parameters = form.parameters.data
            g.db.commit()
            g.log.info(f"sample with id: {sample_id} updated")
            return redirect(url_for('.sample_by_id', sample_id=sample.id))

        if not form.is_submitted():
            # Populate form with current set sample values
            form.version.data = sample.upload.version.id
            form.platform.data = sample.upload.platform.name
            form.notes.data = sample.upload.notes
            form.parameters.data = sample.upload.parameters

        return {
            'sample': sample,
            'form': form
        }

    raise SampleNotFoundException(f"Sample with id {sample_id} not found")


@mod_sample.route('/delete/<sample_id>', methods=['GET', 'POST'])
@login_required
@check_access_rights([Role.admin])
@template_renderer()
def delete_sample(sample_id):
    """
    Delete sample, required admin role.

    :param sample_id: id of the sample
    :type sample_id: int
    :raises SampleNotFoundException: when sample id is not found
    :return: form to edit sample
    :rtype: dict
    """
    from run import config
    sample = Sample.query.filter(Sample.id == sample_id).first()
    if sample is not None:
        # Process or render form
        form = DeleteSampleForm(request.form)
        if form.validate_on_submit():
            # Delete all files (sample, media info & additional files
            basedir = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'TestFiles')
            os.remove(os.path.join(basedir, 'media', sample.sha + '.xml'))
            for extra in sample.extra_files:
                os.remove(os.path.join(basedir, 'extra', extra.filename))

            os.remove(os.path.join(basedir, sample.filename))
            g.db.delete(sample)
            g.db.commit()
            g.log.warning(f"sample with id: {sample_id} deleted")
            return redirect(url_for('.index'))

        return {
            'sample': sample,
            'form': form
        }
    raise SampleNotFoundException(f"Sample with id {sample_id} not found")


@mod_sample.route('/delete/<sample_id>/additional/<additional_id>', methods=['GET', 'POST'])
@login_required
@check_access_rights([Role.admin])
@template_renderer()
def delete_sample_additional(sample_id, additional_id):
    """
    Delete sample's additional, required admin role.

    :param sample_id: id of the sample
    :type sample_id: int
    :param additional_id: id of the sample's additional
    :type additional_id: int
    :raises SampleNotFoundException: when sample id is not found
    :return: form to edit sample
    :rtype: dict
    """
    from run import config
    sample = Sample.query.filter(Sample.id == sample_id).first()
    if sample is not None:
        extra = ExtraFile.query.filter(ExtraFile.id == additional_id).first()
        if extra is not None:
            form = DeleteAdditionalSampleForm(request.form)
            if form.validate_on_submit():
                basedir = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'TestFiles')
                os.remove(os.path.join(basedir, 'extra', extra.filename))
                g.db.delete(extra)
                g.db.commit()
                g.log.warning(f"additional with id: {additional_id} for sample with id: {sample_id} deleted")
                return redirect(url_for('.sample_by_id', sample_id=sample.id))

            return {
                'sample': sample,
                'extra': extra,
                'form': form
            }
        raise SampleNotFoundException(f"Extra file {additional_id} for sample {sample.id} not found")
    raise SampleNotFoundException(f"Sample with id {sample_id} not found")
