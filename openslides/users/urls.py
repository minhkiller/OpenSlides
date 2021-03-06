from django.conf.urls import patterns, url

from . import views

urlpatterns = patterns(
    '',
    # User
    url(r'^$',
        views.UserListView.as_view(),
        name='user_list'),

    url(r'^new/$',
        views.UserCreateView.as_view(),
        name='user_create'),

    url(r'^new_multiple/$',
        views.UserMultipleCreateView.as_view(),
        name='user_create_multiple'),

    url(r'^(?P<pk>\d+)/$',
        views.UserDetailView.as_view(),
        name='user_detail'),

    url(r'^(?P<pk>\d+)/edit/$',
        views.UserUpdateView.as_view(),
        name='user_update'),

    url(r'^(?P<pk>\d+)/del/$',
        views.UserDeleteView.as_view(),
        name='user_delete'),

    url(r'^(?P<pk>\d+)/reset_password/$',
        views.ResetPasswordView.as_view(),
        name='user_reset_password'),

    url(r'^(?P<pk>\d+)/status/activate/$',
        views.SetUserStatusView.as_view(),
        {'action': 'activate'},
        name='user_status_activate'),

    url(r'^(?P<pk>\d+)/status/deactivate/$',
        views.SetUserStatusView.as_view(),
        {'action': 'deactivate'},
        name='user_status_deactivate'),

    url(r'^(?P<pk>\d+)/status/toggle/$',
        views.SetUserStatusView.as_view(),
        {'action': 'toggle'},
        name='user_status_toggle'),

    url(r'^csv_import/$',
        views.UserCSVImportView.as_view(),
        name='user_csv_import'),

    # Group
    url(r'^group/$',
        views.GroupListView.as_view(),
        name='group_list'),

    url(r'^group/new/$',
        views.GroupCreateView.as_view(),
        name='group_create'),

    url(r'^group/(?P<pk>\d+)/$',
        views.GroupDetailView.as_view(),
        name='group_detail'),

    url(r'^group/(?P<pk>\d+)/edit/$',
        views.GroupUpdateView.as_view(),
        name='group_update'),

    url(r'^group/(?P<pk>\d+)/del/$',
        views.GroupDeleteView.as_view(),
        name='group_delete'),

    # PDF
    url(r'^print/$',
        views.UsersListPDF.as_view(),
        name='user_print'),

    url(r'^passwords/print/$',
        views.UsersPasswordsPDF.as_view(),
        name='print_passwords'),
)
