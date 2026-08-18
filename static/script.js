// static/script.js

// Получаем переменные из data-атрибутов или глобальных переменных
const userThemeFromServer = document.body.dataset.userTheme || 'light';
const isUserAuthenticated = document.body.dataset.isAuthenticated === 'true';

// Управление темой
(function() {
    const savedTheme = localStorage.getItem('forum_theme');
    if (savedTheme === 'dark') {
        document.body.classList.add('dark-theme');
    } else if (savedTheme === 'light') {
        document.body.classList.remove('dark-theme');
    } else if (isUserAuthenticated && userThemeFromServer === 'dark') {
        document.body.classList.add('dark-theme');
        localStorage.setItem('forum_theme', 'dark');
    }
})();

window.setTheme = function(theme) {
    if (theme === 'dark') {
        document.body.classList.add('dark-theme');
        localStorage.setItem('forum_theme', 'dark');
    } else {
        document.body.classList.remove('dark-theme');
        localStorage.setItem('forum_theme', 'light');
    }
    fetch('/update_theme', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme: theme })
    }).catch(function(err) {
        console.error('Ошибка сохранения темы:', err);
    });
};

// Поиск
var searchInput = document.getElementById('searchInput');
if (searchInput) {
    searchInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            var q = this.value.trim();
            if (q) {
                window.location.href = '/search?q=' + encodeURIComponent(q);
            }
        }
    });
}

// Кнопка новой темы
var createBtn = document.getElementById('createTopicBtn');
if (createBtn) {
    createBtn.addEventListener('click', function(e) {
        e.preventDefault();
        var nextInput = document.getElementById('loginNext');
        if (nextInput) {
            nextInput.value = '/create-post';
        }
        new bootstrap.Modal(document.getElementById('loginModal')).show();
    });
}

// AJAX-вход
var loginForm = document.getElementById('loginForm');
if (loginForm) {
    loginForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        document.getElementById('loginUsernameError').innerHTML = '';
        document.getElementById('loginPasswordError').innerHTML = '';
        var formData = new FormData(loginForm);
        try {
            var response = await fetch('/login', {
                method: 'POST',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                body: formData
            });
            var data = await response.json();
            if (data.success) {
                window.location.href = data.redirect || '/';
            } else {
                if (data.errors) {
                    if (data.errors.username) {
                        document.getElementById('loginUsernameError').innerHTML = data.errors.username[0];
                    }
                    if (data.errors.password) {
                        document.getElementById('loginPasswordError').innerHTML = data.errors.password[0];
                    }
                }
                if (data.message) {
                    document.getElementById('loginPasswordError').innerHTML = data.message;
                }
            }
        } catch (error) {
            alert('Ошибка входа');
        }
    });
}

// AJAX-регистрация
var registerForm = document.getElementById('registerForm');
if (registerForm) {
    registerForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        document.getElementById('usernameError').innerHTML = '';
        document.getElementById('emailError').innerHTML = '';
        document.getElementById('passwordError').innerHTML = '';
        document.getElementById('password2Error').innerHTML = '';
        var formData = new FormData(registerForm);
        try {
            var response = await fetch('/register', {
                method: 'POST',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                body: formData
            });
            var data = await response.json();
            if (data.success) {
                window.location.href = data.redirect || '/';
            } else {
                if (data.errors) {
                    if (data.errors.username) {
                        document.getElementById('usernameError').innerHTML = data.errors.username[0];
                    }
                    if (data.errors.email) {
                        document.getElementById('emailError').innerHTML = data.errors.email[0];
                    }
                    if (data.errors.password) {
                        document.getElementById('passwordError').innerHTML = data.errors.password[0];
                    }
                    if (data.errors.password2) {
                        document.getElementById('password2Error').innerHTML = data.errors.password2[0];
                    }
                }
            }
        } catch (error) {
            alert('Ошибка регистрации');
        }
    });
}

// Уведомления
var notifDropdown = document.getElementById('notifDropdown');
if (notifDropdown) {
    notifDropdown.addEventListener('click', function() {
        fetch('/notifications/read', { method: 'POST' });
    });
}


// Установка баннера из data-атрибута
document.querySelectorAll('.profile-banner.has-banner').forEach(function(banner) {
    var url = banner.getAttribute('data-banner-url');
    if (url) {
        banner.style.backgroundImage = 'url(' + url + ')';
    }
});