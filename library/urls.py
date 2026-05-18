from django.urls import path

from . import views


urlpatterns = [
    path("", views.home, name="home"),
    path("signup/", views.signup_view, name="signup"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("request-access/", views.request_access, name="request_access"),
    path(
        "books/<str:book_id>/request-access/",
        views.request_book_access,
        name="request_book_access",
    ),
    path("books/<str:book_id>/thumbnail/", views.book_thumbnail, name="book_thumbnail"),
    path("books/<str:book_id>/open/", views.open_pdf, name="open_pdf"),
    path("books/<str:book_id>/", views.viewer, name="viewer"),
    path("books/<str:book_id>/file/", views.pdf_stream, name="pdf_stream"),
    path("site-admin/", views.admin_dashboard, name="admin_dashboard"),
    path("site-admin/upload/", views.upload_pdf, name="upload_pdf"),
    path(
        "site-admin/telegram-admins/add/",
        views.add_telegram_admin,
        name="add_telegram_admin",
    ),
    path(
        "site-admin/telegram-webhook/setup/",
        views.setup_telegram_webhook,
        name="setup_telegram_webhook",
    ),
    path(
        "site-admin/telegram-updates/sync/",
        views.sync_telegram_updates,
        name="sync_telegram_updates",
    ),
    path(
        "site-admin/telegram-admins/<str:admin_id>/remove/",
        views.remove_telegram_admin,
        name="remove_telegram_admin",
    ),
    path(
        "site-admin/requests/<str:request_id>/<str:decision>/",
        views.decide_request,
        name="decide_request",
    ),
    path(
        "site-admin/books/<str:book_id>/thumbnail/",
        views.update_book_thumbnail,
        name="update_book_thumbnail",
    ),
    path(
        "site-admin/books/<str:book_id>/thumbnail/remove/",
        views.remove_book_thumbnail,
        name="remove_book_thumbnail",
    ),
    path("site-admin/books/<str:book_id>/delete/", views.delete_book, name="delete_book"),
    path(
        "telegram/webhook/<str:secret>/",
        views.telegram_webhook,
        name="telegram_webhook",
    ),
]
