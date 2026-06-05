# Universal Clipboard (Android → Mac)

## Что это
Утилита для передачи файлов и скриншотов с Android на Mac.
Сценарий v1: на Android жмёшь «Поделиться» → файл летит на Mac →
сразу попадает в буфер обмена мака (и сохраняется в папку).

## Стек
- **Mac (приоритет сейчас):** Python. FastAPI-сервер принимает файл по HTTP,
  кладёт картинку в системный буфер через pyobjc (NSPasteboard).
  Обёрнут в menu bar app на rumps (иконка в верхней панели, не в доке).
  Упаковка в .app через py2app.
- **Android (позже):** Kotlin, минимальное приложение-приёмник с intent-filter
  на ACTION_SEND, шлёт multipart POST на айпи мака.
- **Связь:** локальная сеть сейчас; Tailscale потом, чтобы работало откуда угодно.

## Принципы
- Я знаю Python и немного C++, Kotlin/Swift не знаю — объясняй незнакомые куски.
- Защита: общий секретный токен в заголовке x-token на всех запросах.
- Начинаем с Mac-части. Android — следующий этап. Не забегай вперёд.

## Текущий статус
MVP работает в обе стороны:
- **Android → Mac:** Share Sheet + кнопка в уведомлении + QS-плитка. Файл/текст/картинка
  летят на Mac, картинка попадает в буфер, файлы сохраняются в ~/Downloads/AndroidDrop.
- **Mac → Android:** Mac следит за буфером (NSPasteboard) и пушит изменения по WebSocket;
  на телефоне уведомление «Copied on Mac» → один тап → контент в буфере Android,
  скриншоты дополнительно сохраняются в Галерею (Pictures/AndroidDrop, Android 10+).
- **Авто-поиск:** Mac объявляет себя по mDNS (`_androiddrop._tcp`), Android находит через
  NsdManager; при смене IP всё чинится само.

Защита от петли: то, что прилетело с телефона и записано в буфер мака, обратно не пушится
(сверка changeCount). Токен `x-token` на всех запросах.

**Шифрование:** весь трафик по HTTPS/WSS. Mac держит самоподписанный серт+ключ
(`~/Library/Application Support/AndroidDrop/`, генерится один раз, mac/tls.py). Android
пинит публичный ключ (SPKI SHA-256) — trust-on-first-use, при смене ключа коннект
отвергается (anti-MITM). Пиним ключ, а не хост, поэтому смена IP не ломает пиннинг.
Кнопка «Reset pairing» в настройках Android сбрасывает пин (при смене мака/серта).
Отпечаток виден в меню мака («Show Security Code») и в `/health`.

## Mac UI
Живёт в строке меню (rumps, Accessory — иконки в доке нет). Пункт меню «Settings…»
открывает окно (AppKit/PyObjC, `mac/window.py`): статус, редактируемый токен, выбор
папки сохранения, тумблер «Send clipboard to Android», Security Code + Copy, «Open
Folder». Пока окно открыто — приложение переключается в Regular (появляется иконка в
доке), при закрытии — обратно в Accessory. Настройки (токен/папка/тумблер) хранятся в
`~/Library/Application Support/AndroidDrop/settings.json` (`mac/settings.py`) — больше
не нужно править config.py; токен при смене надо обновить и на Android.

## Сборка Mac-приложения (.app)
Упаковано через py2app в самодостаточный `AndroidDrop.app` (запускается двойным
кликом, без Python/терминала). Сборка:
```
cd mac && ./build_app.sh        # результат: mac/dist/AndroidDrop.app
```
Конфиг сборки — `mac/setup.py` (`LSUIElement=True` → только иконка в строке меню,
без иконки в доке). Тяжёлые пакеты (fastapi/uvicorn/pydantic/zeroconf/websockets)
перечислены в `packages`, иначе py2app не дотягивает их динамические импорты.
Перетащи `.app` в `/Applications` и открой из Launchpad. Сборка не коммитится (.gitignore).

## Возможные следующие шаги
Tailscale для работы вне локальной сети; иконка-картинка вместо текстовой «⬇»;
авто-запуск при логине (Login Items).