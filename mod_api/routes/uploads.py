"""
Sample upload and the queue an upload sits in until it is described.

POST   /samples/upload            Upload a media file into the queue
GET    /queued-samples            Uploads waiting to be described
GET    /queued-samples/{id}       One queued upload
POST   /queued-samples/{id}/finalize
                                  Turn a queued upload into a sample
POST   /queued-samples/{id}/link  Attach one to an existing sample
DELETE /queued-samples/{id}       Discard a queued upload

Uploading and describing are two steps here for the same reason they are on
the classic pages: the transfer is slow and the metadata needs a CCExtractor
version the uploader may have to go and look up, so the bytes are banked
first and the description follows.
"""

import hashlib
import mimetypes
import os
from uuid import uuid4

import magic
from flask import g, request
from werkzeug.utils import secure_filename

from mod_api import mod_api
from mod_api.middleware.auth import require_scope
from mod_api.middleware.error_handler import make_error_response
from mod_api.middleware.validation import (validate_body,
                                           validate_offset_pagination,
                                           validate_path_id)
from mod_api.models.api_token import Scope
from mod_api.schemas.uploads import QueueLinkSchema, UploadFinalizeSchema
from mod_api.utils import paginated_response, single_response
from mod_auth.models import Role
from mod_home.models import CCExtractorVersion
from mod_sample.models import (ExtraFile, ForbiddenExtension,
                               ForbiddenMimeType, Sample)
from mod_upload.models import Platform, QueuedSample, Upload

# Enough of the file for libmagic to identify it, matching the classic form.
_SNIFF_BYTES = 1024


def _repo(*parts):
    """Build a path inside the sample repository."""
    from run import config

    return os.path.join(config.get('SAMPLE_REPOSITORY', ''), *parts)


def _serialize(queued):
    """Public shape of one queued upload."""
    return {
        'id': queued.id,
        'sha': queued.sha,
        'extension': queued.extension,
        'original_name': queued.original_name,
        'user_id': queued.user_id,
    }


def _forbidden_reason(filename, head):
    """
    Say why an upload is not allowed, or None when it is.

    Runs the same three checks as the classic upload form: the extension on
    the name, the mime type libmagic reads out of the file, and the
    extension that mime type implies. The last one catches a banned format
    renamed to get past the first.
    """
    extension = os.path.splitext(filename)[1].lstrip('.').lower()
    if extension and ForbiddenExtension.query.filter(
            ForbiddenExtension.extension == extension).first() is not None:
        return f"Files with the '{extension}' extension are not accepted."

    mimetype = magic.from_buffer(head, mime=True)
    if ForbiddenMimeType.query.filter(
            ForbiddenMimeType.mimetype == mimetype).first() is not None:
        return f"Files of type '{mimetype}' are not accepted."

    implied = mimetypes.guess_extension(mimetype)
    if implied and ForbiddenExtension.query.filter(
            ForbiddenExtension.extension == implied.lstrip('.')
    ).first() is not None:
        return f"Files of type '{mimetype}' are not accepted."

    return None


@mod_api.route('/samples/upload', methods=['POST'])
@require_scope(Scope.RUNS_WRITE)
def upload_sample():
    """
    Upload a media file into the queue.

    The file is hashed as it is written, because the hash is both the
    duplicate check and the name the sample is stored under, and reading a
    multi-gigabyte upload twice to get it would double the cost of every
    upload.

    An upload that turns out to be forbidden or already known is deleted
    here rather than left in TempFiles for someone to clean up later.
    """
    uploaded = request.files.get('file')
    if uploaded is None or not uploaded.filename:
        return make_error_response(
            'validation_error',
            'Attach the media file as the "file" part of a multipart form.',
            http_status=400)

    filename = secure_filename(uploaded.filename)
    if not filename:
        # secure_filename empties a name made only of dots, separators or
        # whitespace, and an empty name resolves to TempFiles itself.
        return make_error_response(
            'validation_error', 'Unusable file name.', http_status=400)

    # The staging name belongs to this upload alone rather than to the
    # caller's file name: two clients sending the same name at the same
    # time would otherwise write into one file and produce a hash that
    # describes neither.
    temp_path = _repo('TempFiles', f'api-{uuid4().hex}')

    head = uploaded.stream.read(_SNIFF_BYTES)
    uploaded.stream.seek(0)
    reason = _forbidden_reason(filename, head)
    if reason:
        g.log.warning(f'user {g.api_user.id} tried to upload {filename}: '
                      f'{reason}')
        return make_error_response('forbidden', reason, http_status=403)

    digest = hashlib.sha256()
    with open(temp_path, 'wb') as out:
        for chunk in iter(lambda: uploaded.stream.read(8192), b''):
            digest.update(chunk)
            out.write(chunk)
    sha = digest.hexdigest()

    stored = Sample.query.filter(Sample.sha == sha).first()
    queued_already = QueuedSample.query.filter(
        QueuedSample.sha == sha).first()
    if stored is not None or queued_already is not None:
        os.remove(temp_path)
        return make_error_response(
            'conflict',
            'A sample with this content is already uploaded or queued.',
            details={'sha': sha},
            http_status=409)

    extension = os.path.splitext(filename)[1]
    queued = QueuedSample(sha, extension, os.path.splitext(filename)[0],
                          g.api_user.id)
    g.db.add(queued)
    g.db.commit()

    os.rename(temp_path, _repo('QueuedFiles', queued.filename))

    g.log.info(f'sample {sha} queued via API by {g.api_user.id}')
    return single_response(_serialize(queued), http_status=201)


def _visible_queue():
    """Queued uploads the caller may see: their own, or all for an admin."""
    query = QueuedSample.query.filter(
        QueuedSample.user_id == g.api_user.id)
    if g.api_user.role == Role.admin:
        query = QueuedSample.query
    return query.order_by(QueuedSample.id.asc())


@mod_api.route('/queued-samples', methods=['GET'])
@require_scope(Scope.RUNS_READ)
@validate_offset_pagination()
def list_queued_samples(limit=50, offset=0):
    """List uploads waiting to be described. Admins see everyone's."""
    query = _visible_queue()
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return paginated_response(
        [_serialize(q) for q in rows], total, limit, offset)


def _get_queued(queued_id):
    """Look up a queued upload the caller is allowed to see."""
    queued = _visible_queue().filter(QueuedSample.id == queued_id).first()
    if queued is None:
        # Someone else's upload reads as absent rather than forbidden, so
        # the id cannot be used to find out what others have queued.
        return None, make_error_response(
            'not_found', f'Queued sample {queued_id} not found.',
            http_status=404)
    return queued, None


@mod_api.route('/queued-samples/<queued_id>', methods=['GET'])
@require_scope(Scope.RUNS_READ)
@validate_path_id('queued_id')
def get_queued_sample(queued_id):
    """Return one queued upload."""
    queued, err = _get_queued(queued_id)
    if err:
        return err
    return single_response(_serialize(queued))


@mod_api.route('/queued-samples/<queued_id>/finalize', methods=['POST'])
@require_scope(Scope.RUNS_WRITE)
@validate_path_id('queued_id')
@validate_body(UploadFinalizeSchema)
def finalize_queued_sample(queued_id, validated_data=None):
    """
    Turn a queued upload into a sample.

    The file only moves into TestFiles once the rows are committed, so a
    failure part way through leaves the upload in the queue to retry rather
    than a sample row pointing at a file that was never placed.

    Reporting the sample as a GitHub issue, which the classic page offers
    here, is left to the classic page: it needs the platform's GitHub token
    and has nothing to do with getting the sample into the library.
    """
    queued, err = _get_queued(queued_id)
    if err:
        return err

    data = validated_data
    version = CCExtractorVersion.query.filter(
        CCExtractorVersion.version == data['version']).first()
    if version is None:
        return make_error_response(
            'validation_error',
            f"Unknown CCExtractor version: {data['version']}",
            http_status=400)

    source = _repo('QueuedFiles', queued.filename)
    if not os.path.isfile(source):
        return make_error_response(
            'conflict',
            f'The uploaded file for queued sample {queued_id} is missing '
            f'from storage, so it cannot be finalized.',
            http_status=409)

    destination = _repo('TestFiles', queued.filename)
    sample = Sample(queued.sha, queued.extension.lstrip('.'),
                    queued.original_name)
    g.db.add(sample)
    g.db.flush([sample])
    g.db.add(Upload(
        g.api_user.id, sample.id, version.id,
        Platform.from_string(data['platform']),
        data['parameters'], data['notes'],
    ))
    g.db.delete(queued)
    g.db.commit()

    os.rename(source, destination)

    g.log.info(f'queued sample {queued_id} finalized as sample {sample.id} '
               f'via API by {g.api_user.id}')
    return single_response({
        'sample_id': sample.id,
        'sha': sample.sha,
        'original_name': sample.original_name,
    }, http_status=201)


@mod_api.route('/queued-samples/<queued_id>/link', methods=['POST'])
@require_scope(Scope.RUNS_WRITE)
@validate_path_id('queued_id')
@validate_body(QueueLinkSchema)
def link_queued_sample(queued_id, validated_data=None):
    """
    Attach a queued upload to an existing sample as an extra file.

    Used for the material that belongs with a sample without being one, such
    as a subtitle track to compare against. The classic page offered this
    but never carried it out: its confirm step checks permissions and then
    redirects without touching anything, so this is the behaviour it
    described rather than the behaviour it had.

    As with finalize, the file moves only after the row is committed, since
    the stored name is derived from the id the row is given.
    """
    queued, err = _get_queued(queued_id)
    if err:
        return err

    sample_id = validated_data['sample_id']
    sample = Sample.query.filter(Sample.id == sample_id).first()
    if sample is None:
        return make_error_response(
            'not_found', f'Sample {sample_id} not found.', http_status=404)

    source = _repo('QueuedFiles', queued.filename)
    if not os.path.isfile(source):
        return make_error_response(
            'conflict',
            f'The uploaded file for queued sample {queued_id} is missing '
            f'from storage, so it cannot be linked.',
            http_status=409)

    extra = ExtraFile(sample.id, queued.extension.lstrip('.'),
                      queued.original_name)
    g.db.add(extra)
    g.db.flush([extra])
    filename = extra.filename
    g.db.delete(queued)
    g.db.commit()

    os.rename(source, _repo('TestFiles', 'extra', filename))

    g.log.info(f'queued sample {queued_id} linked to sample {sample.id} as '
               f'extra file {extra.id} via API by {g.api_user.id}')
    return single_response({
        'id': extra.id,
        'sample_id': sample.id,
        'filename': filename,
    }, http_status=201)


@mod_api.route('/queued-samples/<queued_id>', methods=['DELETE'])
@require_scope(Scope.RUNS_WRITE)
@validate_path_id('queued_id')
def delete_queued_sample(queued_id):
    """Discard a queued upload and the file behind it."""
    queued, err = _get_queued(queued_id)
    if err:
        return err

    path = _repo('QueuedFiles', queued.filename)
    try:
        os.remove(path)
    except OSError as e:
        # The row goes either way: refusing would leave a queue entry
        # nobody can clear.
        g.log.warning(f'could not delete queued file {path}: {e}')

    g.db.delete(queued)
    g.db.commit()

    g.log.warning(f'queued sample {queued_id} discarded via API by '
                  f'{g.api_user.id}')
    return single_response({'id': int(queued_id), 'deleted': True})
