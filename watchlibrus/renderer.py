from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

DAYS = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY']


def map_day(day):
    return DAYS[day]


class Renderer(object):
    def __init__(self) -> None:
        self._env = Environment(
            loader=PackageLoader('watchlibrus', 'templates'),
            autoescape=select_autoescape()
        )
        self._env.filters['map_day'] = map_day

    def render(self, filename: str, context: Any) -> str:
        template = self._env.get_template(filename)
        return template.render(context)
