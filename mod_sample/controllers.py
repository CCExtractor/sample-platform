"""Logic to fetch sample information, uploading, editing, deleting sample."""

import json
import os
from operator import and_

import requests
from flask import Blueprint, g, make_response, redirect, request, url_for

from decorators import template_renderer
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

mod_sample = Blueprint('sample', __name__)


@mod_sample.before_app_request
def before_app_request():
    """Curate menu items before app request."""
    g.menu_entries['samples'] = {
        'title': 'Sample info',
        'icon': 'object-group',
        'route': 'sample.index'
    }


class SampleNotFoundException(Exception):
    """Custom exception triggered when sample not found."""

    def __init__(self, message):
        Exception.__init__(self)
        self.message = message


def display_sample_info(sample):
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

    raise SampleNotFoundException('Sample with id {id} not found.'.format(id=sample_id))


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

    raise SampleNotFoundException('Sample with hash {hash} not found.'.format(hash=sample_hash))


def serve_file_download(file_name, sub_folder='', content_type='application/octet-stream'):
    """
    Serve sample file for download.

    :param file_name: name of the sample file
    :type file_name: str
    :param sub_folder: name of the subfolder, defaults to ''
    :type sub_folder: str, optional
    :param content_type: type of the content, defaults to 'application/octet-stream'
    :type content_type: str, optional
    :return: sample file
    :rtype: Flask response
    """
    from run import config

    file_path = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'TestFiles', sub_folder, file_name)
    response = make_response()
    response.headers['Content-Description'] = 'File Transfer'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Content-Type'] = content_type
    response.headers['Content-Disposition'] = 'attachment; filename={file_name}'.format(file_name=file_name)
    response.headers['Content-Length'] = os.path.getsize(file_path)
    response.headers['X-Accel-Redirect'] = '/' + os.path.join('media-download', sub_folder, file_name)
    return response


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
        return serve_file_download(sample.filename)
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
            return serve_file_download(sample.sha + '.xml', 'media', 'text/xml')

        raise SampleNotFoundException('Media information for sample {id} not found'.format(id=sample.id))

    raise SampleNotFoundException('Sample with id {id} not found'.format(id=sample_id))


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
        # Fetch additional info
        extra = ExtraFile.query.filter(ExtraFile.id == additional_id).first()
        if extra is not None:
            return serve_file_download(extra.filename, 'extra')
        raise SampleNotFoundException('Extra file {a_id} for sample {s_id} not found'.format(
            a_id=additional_id, s_id=sample.id))
    raise SampleNotFoundException('Sample with id {id} not found'.format(id=sample_id))


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

    raise SampleNotFoundException('Sample with id {id} not found'.format(id=sample_id))


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
            return redirect(url_for('.index'))

        return {
            'sample': sample,
            'form': form
        }
    raise SampleNotFoundException('Sample with id {id} not found'.format(id=sample_id))


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
    :type additiona_id: int
    :raises SampleNotFoundException: when sample id is not found
    :return: form to edit sample
    :rtype: dict
    """
    from run import config
    sample = Sample.query.filter(Sample.id == sample_id).first()
    if sample is not None:
        # Fetch additional info
        extra = ExtraFile.query.filter(ExtraFile.id == additional_id).first()
        if extra is not None:
            # Process or render form
            form = DeleteAdditionalSampleForm(request.form)
            if form.validate_on_submit():
                basedir = os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'TestFiles')
                os.remove(os.path.join(basedir, 'extra', extra.filename))
                g.db.delete(extra)
                g.db.commit()
                return redirect(url_for('.sample_by_id', sample_id=sample.id))

            return {
                'sample': sample,
                'extra': extra,
                'form': form
            }
        raise SampleNotFoundException('Extra file {f_id} for sample {s_id} not found'.format(
            f_id=additional_id, s_id=sample.id))
    raise SampleNotFoundException('Sample with id {id} not found'.format(id=sample_id))
