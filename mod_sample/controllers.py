import os

from flask import Blueprint, make_response

from decorators import template_renderer
from mod_sample.models import Sample, ExtraFile, ForbiddenExtension

mod_sample = Blueprint('sample', __name__)


class SampleNotFoundException(Exception):
    def __init__(self, message):
        Exception.__init__(self)
        self.message = message


def fetch_media_info(sample):
    return []


def display_sample_info(sample):
    media_info = fetch_media_info(sample)
    if media_info is not None:
        return {
            'sample': sample,
            'media': media_info,
            'additional_files': ExtraFile.query.filter(
                ExtraFile.sample_id == sample.id).all()
        }
    raise SampleNotFoundException('Could not load media info')


@mod_sample.errorhandler(SampleNotFoundException)
@template_renderer('sample/sample_not_found.html', 404)
def not_found(error):
    return {
        'message': error.message
    }


@mod_sample.route('/')
@template_renderer()
def index():
    return {
        'samples': Sample.query.all()
    }


@mod_sample.route('/<regex("[0-9]+"):sample_id>')
@template_renderer('sample/sample_info.html')
def sample_by_id(sample_id):
    sample = Sample.query.filter(Sample.id == sample_id).first()
    if sample is not None:
        return display_sample_info(sample)
    raise SampleNotFoundException('Sample with id %s not found.' % sample_id)


@mod_sample.route('/<regex("[A-Za-z0-9]+"):sample_hash>')
@template_renderer('sample/sample_info.html')
def sample_by_hash(sample_hash):
    sample = Sample.query.filter(Sample.sha == sample_hash).first()
    if sample is not None:
        return display_sample_info(sample)
    raise SampleNotFoundException('Sample with hash %s not found.' %
                                  sample_hash)


def serve_file_download(file_name, sub_folder='',
                        content_type='application/octet-stream'):
    from run import config

    file_path = os.path.join(config.get('SAMPLE_REPOSITORY', ''),
                             'TestFiles', sub_folder, file_name)
    response = make_response()
    response.headers['Content-Description'] = 'File Transfer'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Content-Type'] = content_type
    response.headers['Content-Disposition'] = \
        'attachment; filename=%s' % file_name
    response.headers['Content-Length'] = \
        os.path.getsize(file_path)
    response.headers['X-Accel-Redirect'] = \
        '/' + os.path.join('media-download', sub_folder, file_name)
    return response


@mod_sample.route('/download/<sample_id>')
def download_sample(sample_id):
    sample = Sample.query.filter(Sample.id == sample_id).first()
    if sample is not None:
        return serve_file_download(sample.filename)
    raise SampleNotFoundException('Sample not found')


@mod_sample.route('/download/<sample_id>/media-info')
def download_sample_media_info(sample_id):
    from run import config
    sample = Sample.query.filter(Sample.id == sample_id).first()
    if sample is not None:
        # Fetch media info
        media_info_path = os.path.join(
            config.get('SAMPLE_REPOSITORY', ''), 'TestFiles', 'media',
            sample.sha + '.xml')
        if os.path.isfile(media_info_path):
            return serve_file_download(sample.sha + '.xml', 'media',
                                       'text/xml')
        raise SampleNotFoundException('Media information for sample %s not '
                                      'found' % sample.id)
    raise SampleNotFoundException('Sample with id %s not found' % sample_id)


@mod_sample.route('/download/<sample_id>/additional/<additional_id>')
def download_sample_additional(sample_id, additional_id):
    sample = Sample.query.filter(Sample.id == sample_id).first()
    if sample is not None:
        # Fetch additional info
        extra = ExtraFile.query.filter(ExtraFile.id == additional_id).first()
        if extra is not None:
            return serve_file_download(extra.filename, 'extra')
        raise SampleNotFoundException('Extra file %s for sample %s not '
                                      'found' % (additional_id, sample.id))
    raise SampleNotFoundException('Sample with id %s not found' % sample_id)


@mod_sample.route('/edit/<sample_id>', methods=['GET', 'POST'])
def edit_sample(sample_id):
    pass


@mod_sample.route('/delete/<sample_id>')
def delete_sample(sample_id):
    pass


@mod_sample.route('/delete/<sample_id>/additional/<additional_id>')
def delete_sample_additional(sample_id, additional_id):
    pass
