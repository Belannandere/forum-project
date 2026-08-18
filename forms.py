# forms.py
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, TextAreaField, BooleanField, SubmitField, SelectField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Optional
from models import User, Category

# ========= РЕГИСТРАЦИЯ =========
class RegistrationForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[
        DataRequired(message='Имя пользователя обязательно'),
        Length(min=3, max=80, message='Имя пользователя должно содержать от 3 до 80 символов')
    ])
    email = StringField('Email', validators=[
        DataRequired(message='Email обязателен')
    ])
    password = PasswordField('Пароль', validators=[
        DataRequired(message='Пароль обязателен'),
        Length(min=6, message='Пароль должен содержать не менее 6 символов')
    ])
    password2 = PasswordField('Повторите пароль', validators=[
        DataRequired(message='Пожалуйста, повторите пароль'),
        EqualTo('password', message='Пароли не совпадают')
    ])
    submit = SubmitField('Зарегистрироваться')

    def validate_username(self, field):
        if User.query.filter_by(username=field.data).first():
            raise ValidationError('Это имя пользователя уже занято')

    def validate_email(self, field):
        email = field.data
        if '@' not in email or '.' not in email.split('@')[-1]:
            raise ValidationError('Некорректный email адрес')
        if User.query.filter_by(email=email).first():
            raise ValidationError('Этот email уже зарегистрирован')

# ========= ВХОД =========
class LoginForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[
        DataRequired(message='Введите имя пользователя')
    ])
    password = PasswordField('Пароль', validators=[
        DataRequired(message='Введите пароль')
    ])
    remember = BooleanField('Запомнить меня')
    submit = SubmitField('Войти')

# ========= ПОСТЫ (ТЕМЫ) =========
class PostForm(FlaskForm):
    title = StringField('Заголовок', validators=[
        DataRequired(message='Заголовок не может быть пустым'),
        Length(max=200, message='Заголовок не должен превышать 200 символов')
    ])
    content = TextAreaField('Содержание', validators=[
        DataRequired(message='Содержание не может быть пустым')
    ])
    category = SelectField('Категория', coerce=int, validators=[
        DataRequired(message='Выберите категорию')
    ])
    media = FileField('Прикрепить изображение или видео', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'mp4', 'webm', 'mov'], 
                    message='Допустимые форматы: JPG, JPEG, PNG, GIF, MP4, WEBM, MOV')
    ])
    submit = SubmitField('Опубликовать')

# ========= КОММЕНТАРИИ =========
class CommentForm(FlaskForm):
    content = TextAreaField('Комментарий', validators=[
        DataRequired(message='Комментарий не может быть пустым')
    ])
    submit = SubmitField('Отправить')

# ========= КАТЕГОРИИ =========
class CategoryForm(FlaskForm):
    name = StringField('Название категории', validators=[
        DataRequired(message='Название категории обязательно'),
        Length(max=100, message='Название не должно превышать 100 символов')
    ])
    description = TextAreaField('Описание', validators=[Optional()])
    color = StringField('Цвет (hex)', validators=[Optional()], default='#4a6741')
    icon_class = StringField('Иконка (Font Awesome)', validators=[Optional()], default='fas fa-folder')
    submit = SubmitField('Создать')

# ========= ПОИСК =========
class SearchForm(FlaskForm):
    query = StringField('Поиск', validators=[
        DataRequired(message='Введите поисковый запрос')
    ])
    submit = SubmitField('Найти')

# ========= РЕДАКТИРОВАНИЕ ПРОФИЛЯ =========
class EditProfileForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[
        DataRequired(message='Имя пользователя обязательно'),
        Length(min=3, max=80, message='Имя пользователя должно содержать от 3 до 80 символов')
    ])
    bio = TextAreaField('О себе', validators=[Optional(), Length(max=500, message='Максимум 500 символов')])
    avatar = FileField('Аватарка', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], message='Допустимые форматы: JPG, JPEG, PNG, GIF')
    ])
    banner = FileField('Баннер профиля', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], message='Допустимые форматы: JPG, JPEG, PNG, GIF')
    ])
    remove_avatar = BooleanField('Удалить текущую аватарку')
    remove_banner = BooleanField('Удалить текущий баннер')
    submit = SubmitField('Сохранить изменения')

    def __init__(self, original_username, *args, **kwargs):
        super(EditProfileForm, self).__init__(*args, **kwargs)
        self.original_username = original_username

    def validate_username(self, username):
        if username.data != self.original_username and User.query.filter_by(username=username.data).first():
            raise ValidationError('Это имя пользователя уже занято')

# ========= СМЕНА EMAIL =========
class ChangeEmailForm(FlaskForm):
    email = StringField('Новый Email', validators=[
        DataRequired(message='Email обязателен')
    ])
    submit = SubmitField('Сменить email')

    def validate_email(self, field):
        email = field.data
        if '@' not in email or '.' not in email.split('@')[-1]:
            raise ValidationError('Некорректный email адрес')
        if User.query.filter_by(email=email).first():
            raise ValidationError('Этот email уже используется')

# ========= СМЕНА ПАРОЛЯ =========
class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Текущий пароль', validators=[
        DataRequired(message='Введите текущий пароль')
    ])
    new_password = PasswordField('Новый пароль', validators=[
        DataRequired(message='Новый пароль обязателен'),
        Length(min=6, message='Новый пароль должен содержать не менее 6 символов')
    ])
    confirm_password = PasswordField('Подтвердите пароль', validators=[
        DataRequired(message='Повторите новый пароль'),
        EqualTo('new_password', message='Пароли не совпадают')
    ])
    submit = SubmitField('Сменить пароль')