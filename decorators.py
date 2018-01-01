from datetime import date
from functools import wraps
from flask import request, g, render_template


def get_menu_entries(user, title, icon, access=None, route='', all_entries=None):
    """
    Parses a given set of entries and checks which ones the user can access.

    :param access: Grant access to these roles. Empty means public access.
    :type access: list[str]
    :param user: The user object.
    :type user: mod_auth.models.User
    :param title: The title of the root menu entry.
    :type title: str
    :param icon: The icon of the root menu entry.
    :type icon: str
    :param route: The route of the root menu entry.
    :type route: str
    :param all_entries: The sub entries for this menu entry.
    :type all_entries: list[dict]
    :return: A dict consisting of the menu entry.
    :rtype: dict
    """
    if all_entries is None:
        all_entries = []
    if access is None:
        access = []
    result = {
        'title': title,
        'icon': icon
    }
    allowed_entries = []
    passed = False
    if user is not None:
        if len(route) > 0:
            result['route'] = route
            passed = len(access) == 0 or user.role in access
        else:
            for entry in all_entries:
                # TODO: make this recursive if necessary
                if len(entry['access']) == 0 or user.role in entry['access']:
                    allowed_entries.append(entry)
            if len(allowed_entries) > 0:
                result['entries'] = allowed_entries
                passed = True
    elif len(access) == 0:
        if len(route) > 0:
            result['route'] = route
            passed = True
        else:
            for entry in all_entries:
                # TODO: make this recursive if necessary
                if len(entry['access']) == 0:
                    allowed_entries.append(entry)
            if len(allowed_entries) > 0:
                result['entries'] = allowed_entries
                passed = True

    return result if passed else {}


def template_renderer(template=None, status=200):
    """
    Decorator to render a template.

    :param template: The template if it's not equal to the name of the endpoint.
    :type template: str
    :param status: The return code
    :type status: int
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            template_name = template
            if template_name is None:
                template_name = request.endpoint.replace('.', '/') + '.html'
            ctx = f(*args, **kwargs)

            if ctx is None:
                ctx = {}
            elif not isinstance(ctx, dict):
                return ctx
            # Add default values
            ctx['applicationName'] = 'CCExtractor CI platform'
            ctx['applicationVersion'] = getattr(g, 'version', 'Unknown')
            ctx['currentYear'] = date.today().strftime('%Y')
            try:
                from build_commit import build_commit
            except ImportError:
                build_commit = 'Unknown'
            ctx['build_commit'] = build_commit
            user = getattr(g, 'user', None)
            ctx['user'] = user
            # Create menu entries
            menu_entries = getattr(g, 'menu_entries', {})
            ctx['menu'] = [
                menu_entries.get('home', {}),
                menu_entries.get('samples', {}),
                menu_entries.get('upload', {}),
                menu_entries.get('tests', {}),
                menu_entries.get('regression', {}),
                menu_entries.get('config', {}),
                menu_entries.get('account', {}),
                menu_entries.get('auth', {})
            ]
            ctx['active_route'] = request.endpoint

            # Render template & return
            return render_template(template_name, **ctx), status

        return decorated_function

    return decorator
