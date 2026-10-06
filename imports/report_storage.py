import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from django.utils.functional import cached_property


@deconstructible
class ImportReportStorage(FileSystemStorage):
    @cached_property
    def base_location(self):
        return settings.IMPORT_REPORT_ROOT

    @cached_property
    def location(self):
        return os.path.abspath(self.base_location)

    def _clear_cached_properties(self, setting, **kwargs):
        super()._clear_cached_properties(setting, **kwargs)
        if setting == 'IMPORT_REPORT_ROOT':
            self.__dict__.pop('base_location', None)
            self.__dict__.pop('location', None)
