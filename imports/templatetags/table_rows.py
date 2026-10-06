from django import template

register = template.Library()


@register.filter
def row_number(counter, page):
    """Continue record numbering from the first result on the current page."""
    return page.start_index() + counter - 1
