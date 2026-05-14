from io import BytesIO
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.files.base import File
from django.core.files.storage import Storage
from django.utils.text import get_valid_filename


class CloudinaryDeliveryError(Exception):
    pass


class CloudinaryRawStorage(Storage):
    """Store uploaded protected media as Cloudinary raw assets."""

    def __init__(self, prefix=None):
        self.prefix = (prefix or getattr(settings, "CLOUDINARY_STORAGE_PREFIX", "")).strip("/")

    def _cloudinary_modules(self):
        import cloudinary.api
        import cloudinary.exceptions
        import cloudinary.uploader
        import cloudinary.utils

        return cloudinary.api, cloudinary.exceptions, cloudinary.uploader, cloudinary.utils

    def _clean_name(self, name):
        parts = [get_valid_filename(part) for part in str(name).replace("\\", "/").split("/")]
        parts = [part for part in parts if part and part not in {".", ".."}]
        return "/".join(parts)

    def _public_id(self, name):
        clean_name = self._clean_name(name)
        if self.prefix:
            return f"{self.prefix}/{clean_name}"
        return clean_name

    def public_id_for_name(self, name):
        return self._public_id(name)

    def _open(self, name, mode="rb"):
        if "b" not in mode:
            raise ValueError("CloudinaryRawStorage only supports binary reads.")

        request = Request(self.url(name), headers={"User-Agent": "pdf-library"})
        with urlopen(request, timeout=getattr(settings, "CLOUDINARY_DOWNLOAD_TIMEOUT", 20)) as response:
            return File(BytesIO(response.read()), name=name)

    def _save(self, name, content):
        _, _, uploader, _ = self._cloudinary_modules()
        clean_name = self._clean_name(name)
        public_id = self._public_id(clean_name)

        if hasattr(content, "seek"):
            content.seek(0)

        uploader.upload_large(
            content,
            public_id=public_id,
            resource_type="raw",
            overwrite=False,
            use_filename=False,
            unique_filename=False,
            filename=clean_name.rsplit("/", 1)[-1],
            chunk_size=getattr(settings, "CLOUDINARY_UPLOAD_CHUNK_SIZE", 6 * 1024 * 1024),
        )
        return clean_name

    def delete(self, name):
        if not name:
            return

        _, _, uploader, _ = self._cloudinary_modules()
        uploader.destroy(self._public_id(name), resource_type="raw", invalidate=True)

    def exists(self, name):
        api, exceptions, _, _ = self._cloudinary_modules()
        try:
            api.resource(self._public_id(name), resource_type="raw")
        except exceptions.NotFound:
            return False
        return True

    def size(self, name):
        api, _, _, _ = self._cloudinary_modules()
        resource = api.resource(self._public_id(name), resource_type="raw")
        return int(resource.get("bytes") or 0)

    def url(self, name):
        _, _, _, utils = self._cloudinary_modules()
        url, _ = utils.cloudinary_url(
            self._public_id(name),
            resource_type="raw",
            secure=True,
        )
        return url

    def get_available_name(self, name, max_length=None):
        return super().get_available_name(self._clean_name(name), max_length=max_length)

    def get_valid_name(self, name):
        return get_valid_filename(name)


def cloudinary_range_response(name, start, end):
    headers = {
        "Range": f"bytes={start}-{end}",
        "User-Agent": "pdf-library",
    }
    return cloudinary_asset_response(name, headers=headers)


def split_public_id_format(public_id):
    tail = public_id.rsplit("/", 1)[-1]
    if "." not in tail:
        return public_id, ""

    base, extension = public_id.rsplit(".", 1)
    return base, extension.lower()


def private_download_urls(storage, name):
    _, _, _, utils = storage._cloudinary_modules()
    public_id = storage.public_id_for_name(name)
    base_public_id, extension = split_public_id_format(public_id)
    options = {
        "resource_type": "raw",
        "type": "upload",
        "expires_at": int(utils.now()) + 300,
    }

    if extension:
        yield utils.private_download_url(base_public_id, extension, **options)
        yield utils.private_download_url(public_id, extension, **options)


def open_cloudinary_url(url, headers):
    return urlopen(
        Request(url, headers=headers),
        timeout=getattr(settings, "CLOUDINARY_DOWNLOAD_TIMEOUT", 20),
    )


def cloudinary_asset_response(name, headers=None):
    storage = CloudinaryRawStorage()
    headers = headers or {"User-Agent": "pdf-library"}
    errors = []

    urls = [storage.url(name)]
    urls.extend(private_download_urls(storage, name))
    for url in urls:
        try:
            response = open_cloudinary_url(url, headers)
            return response, response.headers
        except HTTPError as error:
            errors.append(f"{error.code} {error.reason}")
            error.close()

    raise CloudinaryDeliveryError(
        "Could not fetch Cloudinary asset. Cloudinary may be blocking PDF delivery. "
        "In Cloudinary Console, enable Security > Allow delivery of PDF and ZIP files, "
        "or verify signed download access. Upstream errors: " + " | ".join(errors)
    )


def cloudinary_file_response(name):
    return cloudinary_asset_response(name)
