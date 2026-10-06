"""State-only adoption of existing tables during the domain app split.

Keep this migration support module stable: historical migrations import it.
"""
from django.db.migrations.operations.base import Operation


class AdoptModels(Operation):
    reduces_to_sql = False
    reversible = True

    def __init__(self, model_names):
        self.model_names = model_names

    def state_forwards(self, app_label, state):
        for name in self.model_names:
            original = state.models['imports', name.lower()]
            adopted = original.clone()
            adopted.app_label = app_label
            adopted.options.setdefault('db_table', 'imports_' + name.lower())
            state.models[app_label, name.lower()] = adopted
        state.__dict__.pop('apps', None)
        state.is_delayed = False

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        pass

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        pass

    def describe(self):
        return 'Adopt existing financial tables without creating or copying them'


class FinalizeDomainSplit(Operation):
    reduces_to_sql = False
    reversible = True

    def __init__(self, model_apps):
        self.model_apps = model_apps

    def state_forwards(self, app_label, state):
        mapping = {'imports.' + name.lower(): target + '.' + name.lower()
                   for name, target in self.model_apps.items()}
        for name in self.model_apps:
            del state.models['imports', name.lower()]
        for key, model in list(state.models.items()):
            cloned = model.clone()
            for name, field in list(cloned.fields.items()):
                if field.is_relation:
                    target = field.remote_field.model
                    if isinstance(target, str) and target.lower() in mapping:
                        field = field.clone()
                        field.remote_field.model = mapping[target.lower()]
                        cloned.fields[name] = field
            state.models[key] = cloned
        state.__dict__.pop('apps', None)
        state.is_delayed = False

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        pass

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        pass

    def describe(self):
        return 'Retarget model relations and retire the old imports model states'
