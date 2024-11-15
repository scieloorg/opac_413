# coding: utf-8

from flask_babel import gettext as _
from webapp import controllers
from wtforms import fields, form, validators


class LoginForm(form.Form):
    email = fields.StringField(
        _("Email"), validators=[validators.InputRequired(), validators.email()]
    )
    password = fields.PasswordField(_("Senha"), validators=[validators.InputRequired()])

    def validate_password(self, field):
        user = controllers.get_user_by_email(self.email.data)
        if user is None:
            raise validators.ValidationError(_("Usuário inválido"))
        if not user.is_correct_password(self.password.data):
            raise validators.ValidationError(_("Senha inválida"))


class EmailForm(form.Form):
    email = fields.StringField(_("Email"), validators=[validators.email()])


class PasswordForm(form.Form):
    password = fields.PasswordField(_("Senha"), validators=[validators.InputRequired()])
