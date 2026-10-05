from django import template

register = template.Library()


@register.filter
def filename_parts(value):
    """Keep the extension separate so only the filename stem is ellipsized."""
    name = str(value or '')
    stem, dot, extension = name.rpartition('.')
    if stem and extension:
        return stem, dot + extension
    return name, ''
