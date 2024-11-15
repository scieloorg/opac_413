# coding: utf-8

import logging

import flask_admin
import rq_dashboard
# import rq_scheduler_dashboard
from elasticapm.contrib.flask import ElasticAPM
from flask import Flask, flash, redirect, request, url_for
from flask_babel import Babel, lazy_gettext
from flask_caching import Cache
from flask_htmlmin import HTMLMIN
from flask_login import LoginManager, current_user
from flask_mail import Mail
from flask_mongoengine2 import MongoEngine
from flask_sqlalchemy import SQLAlchemy
from opac_schema.v1.models import (
    Article,
    AuditLogEntry,
    Collection,
    Issue,
    Journal,
    News,
    Pages,
    PressRelease,
    Sponsor,
)
from raven.contrib.flask import Sentry
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.routing import BaseConverter
# from webapp.main.views import get_locale

login_manager = LoginManager()
dbmongo = MongoEngine()
dbsql = SQLAlchemy()
mail = Mail()
babel = Babel()
sentry = Sentry()
cache = Cache()


from .main import custom_filters  # noqa

logger = logging.getLogger(__name__)


class RegexConverter(BaseConverter):
    def __init__(self, url_map, *items):
        super(RegexConverter, self).__init__(url_map)
        self.regex = items[0]


def configure_apm_agent(app):
    """Configura e inicia o agente de introspecção do APM."""
    from .utils import asbool

    if not app.config.get("APM_ENABLED"):
        logger.debug(
            "APM Agent is disabled. To enable it configure the APM_ENABLED option."
        )
        return

    APM_CONFIG_KEYS_INFO = (
        ("SERVER_URL", True, str),
        ("SERVICE_NAME", False, str),
        ("SECRET_TOKEN", False, str),
        ("ENVIRONMENT", False, str),
        ("SERVICE_VERSION", False, str),
        ("FILTER_EXCEPTION_TYPES", False, str),
        ("TRANSACTIONS_IGNORE_PATTERNS", False, str),
        ("SERVER_TIMEOUT", False, str),
        ("HOSTNAME", False, str),
        ("COLLECT_LOCAL_VARIABLES", False, str),
        ("LOCAL_VAR_MAX_LENGTH", False, int),
        ("CAPTURE_BODY", False, str),
        ("CAPTURE_HEADERS", False, asbool),
        ("TRANSACTION_MAX_SPANS", False, int),
        ("STACK_TRACE_LIMIT", False, int),
        ("DEBUG", False, asbool),
        ("DISABLE_SEND", False, asbool),
        ("INSTRUMENT", False, asbool),
        ("VERIFY_SERVER_CERT", False, asbool),
    )
    apm_config = {}

    for apm_key, required, cast in APM_CONFIG_KEYS_INFO:
        key = "APM_%s" % apm_key
        value = app.config.get(key)

        if value is None or (isinstance(value, str) and len(value) == 0):
            if required:
                raise ValueError(
                    "Could not setup APM Agent. The key '%s' is required, "
                    "please configure it." % key
                ) from None
            continue

        try:
            _value = cast(value)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "Could not set the key '%s' with value '%s'. "
                "The cast function raise the exception '%s'." % (key, value, exc)
            )

        apm_config[apm_key] = _value

    app.config["ELASTIC_APM"] = apm_config
    logger.debug("APM Agent enabled.")

    return ElasticAPM(app)


def create_app():
    app = Flask(
        __name__,
        static_url_path="/static",
        static_folder="static",
        instance_relative_config=False,
    )

    app.url_map.converters["regex"] = RegexConverter

    # Remove strict slash from Werkzeug
    app.url_map.strict_slashes = False

    # Configurações
    app.config.from_object(rq_dashboard.default_settings)
    # app.config.from_object(rq_scheduler_dashboard.default_settings)
    app.config.from_object("webapp.config.default")  # Configuração basica
    app.config.from_envvar("OPAC_CONFIG", silent=True)  # configuração do ambiente
    app.logger.root.setLevel(app.config.get("LOG_LEVEL"))

    configure_apm_agent(app)

    # Sentry:
    if app.config["USE_SENTRY"]:
        dsn = app.config["SENTRY_DSN"]
        sentry.init_app(app, dsn=dsn, logging=True, level=logging.ERROR)

    # login
    login_manager.session_protection = "strong"
    login_manager.login_view = "admin.login_view"
    login_manager.init_app(app)

    # Minificando o HTML
    if app.config["MINIFY_PAGE"]:
        HTMLMIN(app)
        logger.info("HTML minification has been activated.")

    # Registrando os filtros
    app.jinja_env.filters["trans_alpha2"] = custom_filters.trans_alpha2
    app.jinja_env.filters["datetimefilter"] = custom_filters.datetimefilter
    from webapp.main.views import get_locale
    # i18n
    babel.init_app(app, locale_selector=get_locale)
    # Debug Toolbar
    if app.config["DEBUG"]:
        # Toolbar
        from flask_debugtoolbar import DebugToolbarExtension

        toolbar = DebugToolbarExtension()
        toolbar.init_app(app)
    # Mongo
    dbmongo.init_app(app)
    # SQLAlchemy
    dbsql.init_app(app)
    # Emails
    mail.init_app(app)
    # Cache:
    if app.config["CACHE_ENABLED"]:
        cache.init_app(app, config=app.config)
    else:
        app.config["CACHE_TYPE"] = "null"
        cache.init_app(app, config=app.config)

    # Interface do admin
    # from .admin import views
    from webapp.admin import views

    from .models import File, Image, User

    admin = flask_admin.Admin(
        app,
        "OPAC admin",
        index_view=views.AdminIndexView(),
        base_template="admin/opac_base.html",
    )

    admin.add_view(
        views.CollectionAdminView(
            Collection, category=lazy_gettext("Catálogo"), name=lazy_gettext("Coleção")
        )
    )
    admin.add_view(
        views.JournalAdminView(
            Journal, category=lazy_gettext("Catálogo"), name=lazy_gettext("Periódico")
        )
    )
    admin.add_view(
        views.IssueAdminView(
            Issue, category=lazy_gettext("Catálogo"), name=lazy_gettext("Número")
        )
    )
    admin.add_view(
        views.ArticleAdminView(
            Article, category=lazy_gettext("Catálogo"), name=lazy_gettext("Artigo")
        )
    )
    admin.add_view(
        views.SponsorAdminView(
            Sponsor, category=lazy_gettext("Catálogo"), name=lazy_gettext("Financiador")
        )
    )
    admin.add_view(
        views.PressReleaseAdminView(
            PressRelease,
            category=lazy_gettext("Catálogo"),
            name=lazy_gettext("Press Release"),
        )
    )
    admin.add_view(views.NewsAdminView(News, name=lazy_gettext("Notícias")))
    admin.add_view(
        views.FileAdminView(File, dbsql.session, category=lazy_gettext("Ativos"))
    )
    admin.add_view(
        views.ImageAdminView(Image, dbsql.session, category=lazy_gettext("Ativos"))
    )
    admin.add_view(views.PagesAdminView(Pages, name=lazy_gettext("Páginas")))
    admin.add_view(
        views.AuditLogEntryAdminView(
            AuditLogEntry,
            category=lazy_gettext("Gestão"),
            name=lazy_gettext("Auditoria: Páginas"),
        )
    )
    admin.add_view(
        views.UserAdminView(
            User,
            dbsql.session,
            category=lazy_gettext("Gestão"),
            name=lazy_gettext("Usuário"),
        )
    )

    from .main import main as main_bp
    from .main import restapi as rest_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(rest_bp)

    # Setup RQ Dashboard e Scheduler: - mover para um modulo proprio
    @app.before_request
    def check_user_logged_in_or_redirect():
        if not current_user.is_authenticated and request.path in [
            "/admin/scheduler",
            "/admin/workers",
        ]:
            flash("Please log in to access this page.")
            return redirect(url_for("admin.login_view", next=request.path or "/"))

    # Use `with app.app_context()` within the `create_app` definition.
    with app.app_context():
        # app.register_blueprint(
        #     rq_scheduler_dashboard.blueprint, url_prefix="/admin/scheduler"
        # )
        app.register_blueprint(rq_dashboard.blueprint, url_prefix="/admin/workers")
    # FIM do setup RQ Dashboard e Scheduler: - mover para um modulo proprio

    app.wsgi_app = ProxyFix(app.wsgi_app)

    return app
