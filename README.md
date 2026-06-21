# Youtube Music API Bridge

Кроссплатформенный мост для YouTube Music: определяет активный трек, ставит Like и выполняет Previous / Next / Play-Pause через доступный локальный провайдер.

Поддерживаемые провайдеры:

- Windows: локальный API YouTube Music Desktop;
- Android и Wear OS: companion APK, MediaSession и notification actions;
- Chrome/Edge/ChromeOS/macOS: browser extension;
- Linux: MPRIS/playerctl;
- iPhone/iPad: ручной Share Sheet Shortcut;
- fallback Like: официальный YouTube Data API v3.

OAuth client secrets, refresh tokens, reporter tokens, логи и локальные Android SDK-файлы исключены из Git.

## Ограничение официального API

YouTube Data API не публикует состояние проигрывателей пользователя и не имеет метода «что сейчас играет на моих устройствах». В discovery-схеме доступны ресурсы видео, плейлистов, каналов и т. п., но ресурса playback/session/now-playing нет.

Поэтому один скрипт на Windows/Linux **не может узнать**, что сейчас играет в официальном приложении на удаленном Android, WearOS, ChromeOS или другом компьютере. `videos.rate` может поставить оценку только после получения точного `videoId`.

Этот проект не угадывает трек по заголовку: иначе можно поставить Like не тому видео.

## Что работает

| Источник | Определение | Like |
|---|---|---|
| YouTube Music Desktop (`YouTube Music.exe`) на Windows | локальный API `127.0.0.1:26538` | локальный `/api/v1/like` |
| YouTube Music на Android/Wear OS (companion APK; ADB для удалённого вызова) | Android MediaSession/notification | notification PendingIntent `thumbs_up_action` |
| Chrome/Edge на Windows/Linux/macOS/ChromeOS | расширение передает точный `videoId` локальному или удаленному агенту | да |
| Firefox | нужен отдельный Firefox manifest/пакет | пока нет |
| Linux MPRIS | автоматически, если `xesam:url` содержит URL YouTube | да |
| Android/WearOS/ChromeOS YouTube Music app | Google не предоставляет now-playing API | нет |
| другой Windows/Linux/macOS/ChromeOS в браузере | расширение может отправлять reporter на центральный HTTPS endpoint | да |
| iPhone/iPad native YouTube Music | Share Sheet Shortcut sends exact URL to `/api/v1/like-url` | да, с ручным Share |

## Установка агента (Windows и Linux)

Требуется Python 3.10+.

```console
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Linux:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Для Linux MPRIS установите `playerctl` из репозитория дистрибутива.

## OAuth YouTube

1. Создайте проект в Google Cloud Console.
2. Включите **YouTube Data API v3**.
3. Настройте OAuth consent screen.
4. Создайте OAuth Client ID типа **Desktop app**.
5. Скачайте JSON в корень проекта. Поддерживается как `client_secret.json`, так и стандартное длинное имя `client_secret_….apps.googleusercontent.com.json`.

При первом `like-current` браузер запросит доступ. Refresh token хранится в `~/.ytm-like/token.json`. Файлы OAuth исключены из Git.

Авторизацию можно выполнить заранее, без текущего трека:

```console
python ytm_like.py auth
```

### Ошибка 403: приложение не прошло проверку Google

Если OAuth consent screen находится в режиме **Testing**, войти могут только явно добавленные тестовые пользователи:

1. Google Cloud Console → **Google Auth Platform** → **Audience**.
2. В разделе **Test users** нажмите **Add users**.
3. Добавьте Google-аккаунт, которым пользуется YouTube Music, и сохраните.
4. Снова выполните `python ytm_like.py auth`.

Для личного скрипта проходить публичную проверку Google не требуется. В режиме Testing refresh token может иметь ограниченный срок жизни, поэтому иногда потребуется повторная авторизация.

Официальный метод: [`videos.rate`](https://developers.google.com/youtube/v3/docs/videos/rate), rating=`like`, scope=`youtube.force-ssl`.

## Подключение Chrome/Edge

1. Запустите сервер:

   ```console
   python ytm_like.py serve
   ```

2. Откройте `chrome://extensions` (или `edge://extensions`), включите Developer mode и выберите **Load unpacked** → папка `browser-extension`.
3. Откройте настройки расширения и вставьте значение из:

   ```console
   python ytm_like.py token
   ```

4. Откройте YouTube/YouTube Music и запустите трек.

Расширение отправляет только `videoId`, заголовок, автора и статус воспроизведения на `127.0.0.1:8888`. Локальный endpoint защищен случайным bearer token.

После обновления файлов unpacked-расширения нажмите **Reload** на `chrome://extensions`, затем перезагрузите вкладку YouTube Music. Это необходимо, чтобы Chrome заново загрузил content script.

### Браузер на другом устройстве

Агент можно запустить с прослушиванием сети:

```console
python ytm_like.py serve --host 0.0.0.0
```

Перед ним следует поставить HTTPS reverse proxy (Caddy, nginx или аналог), а в настройках расширения указать полный адрес вида `https://music-reporter.example.net/api/v1/report`. Расширение запросит разрешение только для указанного origin.

Не передавайте bearer token через открытый HTTP вне `127.0.0.1`: любой наблюдатель сети сможет подменить текущий трек. Ограничьте endpoint файрволом/VPN и используйте отдельный случайный reporter token.

## Использование

Посмотреть свежий текущий трек:

```console
python ytm_like.py current
```

Поставить Like:

```console
python ytm_like.py like-current
```

Управление активным проигрывателем:

```console
python ytm_like.py previous
python ytm_like.py next
python ytm_like.py play-pause
```

Те же команды доступны по защищённому HTTP endpoint:

```http
POST /api/v1/control
Authorization: Bearer <reporter token>
Content-Type: application/json

{"action":"next"}
```

Допустимые действия: `previous`, `next`, `play-pause`. Маршрутизация: Windows Desktop API → подключённый Android/Wear OS companion → Linux MPRIS → browser extension.

### Приоритет на Windows

При каждом вызове агент проверяет точный executable:

```text
C:\Users\asuma\AppData\Local\Programs\youtube-music\YouTube Music.exe
```

Если процесс запущен, используется API плагина YouTube Music Desktop на `http://127.0.0.1:26538`:

1. `GET /api/v1/song` — точный текущий `videoId` и состояние воспроизведения.
2. `GET /api/v1/like-state` — исходное состояние.
3. `POST /api/v1/like` — установка Like, если он еще не установлен.
4. Повторный `GET /api/v1/like-state` и `GET /api/v1/song` — подтверждение Like и защита от смены трека.

Если этот executable не запущен, используется прежняя цепочка: Linux MPRIS (на Linux), затем свежий browser reporter и официальный YouTube Data API.

При отсутствии Windows Desktop-проигрывателя агент также проверяет подключённые через ADB Android-телефоны/часы с установленным companion APK. YouTube Music не раскрывает `videoId`, но публикует активную MediaSession и собственное notification-действие Like. Агент выполняет PendingIntent, созданный YouTube Music, и проверяет изменение rating/action для того же title/artist. Обычные сторонние приложения не могут вызвать shell-only receiver: он защищён системным `android.permission.DUMP`.

Если в API Server включена стратегия `AUTH_AT_FIRST`, приложение покажет запрос доступа для клиента `ytm-like-script`. Полученный JWT хранится в `~/.ytm-like/desktop-api-token`; также поддерживается переменная `YTM_DESKTOP_TOKEN`.

Совместимые entrypoint-файлы находятся в `compat/like.bat` и `compat/like.php`; оба вызывают единый маршрутизатор `ytm_like.py like-current`.

По умолчанию отчет действителен 30 секунд. Это защищает от Like предыдущему треку, если расширение/проигрыватель перестали отвечать. Настройка: `--max-age 60`.

## Почему нельзя получить «любое устройство» через Google Cast

Google Cast позволяет приложению управлять созданной им Cast-сессией, но не является API истории/активности аккаунта YouTube и не дает произвольному серверному скрипту читать сессии официальных клиентов YouTube Music. Решение для Android/WearOS потребовало бы отдельного companion-приложения с доступом к локальным media notifications; оно все равно не сможет централизованно видеть остальные устройства без собственного канала синхронизации.

## Тесты

```console
python -m unittest discover -s tests -v
```
