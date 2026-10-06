"""Adapter for tests that invoke old migration functions on current test models.

Production migrations always receive their own historical Apps registry.
"""
from django.apps import apps


class LegacyApps:
    DOMAIN_APPS = ('debts', 'payments', 'refunds', 'writeoffs', 'expenses', 'finance', 'references')

    def get_model(self, app_label, model_name):
        if app_label == 'imports':
            for domain in self.DOMAIN_APPS:
                try:
                    return apps.get_model(domain, model_name)
                except LookupError:
                    continue
        return apps.get_model(app_label, model_name)


legacy_apps = LegacyApps()
