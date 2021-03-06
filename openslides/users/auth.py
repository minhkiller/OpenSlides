from django.contrib.auth.models import AnonymousUser as DjangoAnonymousUser, Permission
from django.contrib.auth.context_processors import auth as _auth
from django.contrib.auth import get_user as _get_user
from django.utils.functional import SimpleLazyObject

from openslides.config.api import config


class AnonymousUser(DjangoAnonymousUser):
    """
    Class for anonymous user instances, which have the permissions from the
    Group 'Anonymous' (pk=1).
    """

    def get_all_permissions(self, obj=None):
        """
        Return the permissions a user is granted by his group membership(s).

        Try to return the permissions for the 'Anonymous' group (pk=1).
        """
        perms = Permission.objects.filter(group__pk=1)
        if perms is None:
            return set()
        # TODO: test without order_by()
        perms = perms.values_list('content_type__app_label', 'codename').order_by()
        return set(['%s.%s' % (content_type, codename) for content_type, codename in perms])

    def has_perm(self, perm, obj=None):
        """
        Check if the user has a specific permission
        """
        return (perm in self.get_all_permissions())

    def has_module_perms(self, app_label):
        """
        Check if the user has permissions on the module app_label
        """
        for perm in self.get_all_permissions():
            if perm[:perm.index('.')] == app_label:
                return True
        return False


class AuthenticationMiddleware(object):
    """
    Middleware to get the logged in user in users.

    Uses AnonymousUser instead of the django anonymous user.
    """
    def process_request(self, request):
        """
        Like django.contrib.auth.middleware.AuthenticationMiddleware, but uses
        our own get_user function.
        """
        assert hasattr(request, 'session'), (
            "The authentication middleware requires session middleware "
            "to be installed. Edit your MIDDLEWARE_CLASSES setting to insert "
            "'django.contrib.sessions.middleware.SessionMiddleware' before "
            "'openslides.users.auth.AuthenticationMiddleware'."
        )
        request.user = SimpleLazyObject(lambda: get_user(request))


def get_user(request):
    """
    Gets the user from the request.

    This is a mix of django.contrib.auth.get_user and
    django.contrib.auth.middleware.get_user which uses our anonymous user.
    """
    try:
        return_user = request._cached_user
    except AttributeError:
        # Get the user. If it is a DjangoAnonymousUser, then use our AnonymousUser
        return_user = _get_user(request)
        if config['system_enable_anonymous'] and isinstance(return_user, DjangoAnonymousUser):
            return_user = AnonymousUser()
        request._cached_user = return_user
    return return_user


def auth(request):
    """
    Contextmanager to handle auth.

    Uses the django auth context manager to fill the context.

    Alters the attribute user if the user is not authenticated.
    """
    # Call the django standard auth function, like 'super()'
    context = _auth(request)

    # Change the django anonymous user with our anonymous user if anonymous auth
    # is enabled
    if config['system_enable_anonymous'] and isinstance(context['user'], DjangoAnonymousUser):
        context['user'] = AnonymousUser()

    # Set a context variable that will indicate if anonymous login is possible
    context['os_enable_anonymous_login'] = config['system_enable_anonymous']

    return context
