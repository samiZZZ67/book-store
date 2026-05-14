from io import BytesIO
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.files.base import File
from django.core.files.storage import Storage
from django.utils.text import get_valid_filename


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

        uploader.upload(
            content,
            public_id=public_id,
            resource_type="raw",
            overwrite=False,
            use_filename=False,
            unique_filename=False,
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
    storage = CloudinaryRawStorage()
    request = Request(
        storage.url(name),
        headers={
            "Range": f"bytes={start}-{end}",
            "User-Agent": "pdf-library",
        },
    )
    try:
        response = urlopen(
            request,
            timeout=getattr(settings, "CLOUDINARY_DOWNLOAD_TIMEOUT", 20),
        )
    except HTTPError as error:
        if error.code == 416:
            return None, None
        raise

    return response, response.headers


def cloudinary_file_response(name):
    storage = CloudinaryRawStorage()
    request = Request(
        storage.url(name),
        headers={"User-Agent": "pdf-library"},
    )
    response = urlopen(
        request,
        timeout=getattr(settings, "CLOUDINARY_DOWNLOAD_TIMEOUT", 20),
    )
    return response, response.headers
