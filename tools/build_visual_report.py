"""Build a local, searchable gallery from the final visual review captures."""
import json
from pathlib import Path

out = Path('artifacts/final')
data = json.loads((out / 'metrics.json').read_text(encoding='utf-8'))
cards = []
for page in data['pages']:
    name = page['name']
    before = Path('artifacts/before') / (name + '.png')
    comparison = f'<a href="../before/{name}.png">До изменений</a>' if before.exists() else ''
    cards.append(f'<article data-name="{name}"><a href="{name}.png"><img loading="lazy" src="{name}-viewport.png" alt="{name}"></a><div><strong>{name}</strong><p><a href="{name}.png">Полная страница</a> {comparison}</p></div></article>')
report = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Collectra — визуальный аудит</title>
<style>body{margin:0;font:16px/1.6 "Segoe UI",sans-serif;color:#253146;background:#f3f5f8}main{max-width:1600px;margin:auto;padding:24px}h1{margin:0}h2{font-size:20px}a{color:#425bd2}p{margin:8px 0 16px}input{font:inherit;padding:10px 14px;border:1px solid #aebaca;border-radius:4px;max-width:100%;box-sizing:border-box}section{background:white;border:1px solid #d5dce6;border-radius:4px;padding:20px;margin:20px 0}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:20px}article{background:white;border:1px solid #d5dce6;border-radius:4px;overflow:hidden}article img{width:100%;height:260px;object-fit:contain;background:#edf1f7}article div{padding:16px}article p{font-size:14px}article a+a{margin-left:12px}li+li{margin-top:8px}code{font:inherit;background:#edf0ff;padding:2px 5px}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:10px;border-bottom:1px solid #d5dce6}[hidden]{display:none}details{margin-top:12px}</style>
<main><h1>Collectra — визуальный аудит</h1><p>2 октября 2026 · Проверка реального Django-приложения на изолированной базе с демонстрационными данными.</p>
<section><h2>Что изменено</h2><ul>
<li>Общая типографика: Segoe UI, единая иерархия основного текста, подписей и заголовков, три начертания. Логотип сохранён.</li>
<li>Читаемый основной и второстепенный текст, единые нейтральные цвета, более заметные границы полей и состояния фокуса, ошибок и недоступных действий.</li>
<li>Согласованные размеры кнопок, полей, иконок и чекбоксов. Внутренние отступы и расстояния между группами пересмотрены вместе с размерами.</li>
<li>Заголовки таблиц выделены фоном, начертанием и нижней границей. Суммы выровнены вправо, даты и идентификаторы используют табличные цифры, действия сгруппированы.</li>
<li>Длинные имена и основания переносятся внутри ячеек. Широкие таблицы прокручиваются внутри контейнеров; номер договора остаётся видимым при прокрутке.</li>
<li>На мобильных экранах формы перестроены в одну колонку. Меню, модальные окна и группы действий сохраняют читаемые промежутки.</li></ul></section>
<section><h2>Проблемы, найденные при проверке</h2><table><thead><tr><th>Наблюдение</th><th>Исправление</th></tr></thead><tbody>
<tr><td>Мелкий текст и бледная шапка таблиц</td><td>Общие размеры текста, контрастная шапка, убрано принудительное уменьшение всех вложенных элементов.</td></tr>
<tr><td>Увеличенные элементы теснились в мобильной форме</td><td>Одна колонка, согласованные интервалы между подписями, полями и действиями.</td></tr>
<tr><td>Кнопки нижних панелей стояли вплотную</td><td>Общий flex-контейнер с промежутками и переносом действий.</td></tr>
<tr><td>Длинные ФИО и основания раздували ширину таблиц</td><td>Перенос текстовых ячеек, отдельное выравнивание чисел и дат.</td></tr>
<tr><td>Пустое состояние широкого реестра смещалось за видимую область</td><td>Сообщение центрируется в видимой ширине контейнера таблицы.</td></tr>
<tr><td>Строки результата импорта становились чрезмерно высокими в узком окне</td><td>Минимальная читаемая ширина таблицы, внутренний скролл и перенос ошибок.</td></tr>
<tr><td>Сообщения с жирным заголовком распадались на колонки</td><td>Текст сообщения объединён в общий контейнер.</td></tr>
<tr><td>Фон нижней панели закрывал скругления карточки</td><td>Нижняя панель наследует радиус карточки.</td></tr>
<tr><td>История платежа падала при пустом проверяющем</td><td>Пустое значение отображается как «—». Такая же защита добавлена для отсутствующего автора импорта.</td></tr>
</tbody></table></section>
<section><h2>Проверки и ограничения</h2><p>SCREENS состояний на широком экране, ноутбуке, узком окне и мобильном: 1920×1080, 1366×900, 900×900, 390×844. Сохранены полные страницы и видимая область экрана. Нет горизонтального переполнения страниц и ошибок JavaScript.</p>
<p><code>manage.py check</code> и <code>git diff --check</code> проходят. Тесты: 51/52. Единственный оставшийся сбой — <code>DebtListTests.test_page_filters_by_search_and_status</code>, ожидающий отсутствующее поле <code>debt-search</code>. Он воспроизводится в исходной версии. Исходная версия имела дополнительно два сбоя: пустой проверяющий и проверка текстового заголовка «Автор», записанного HTML-сущностями; оба устранены в слое отображения.</p>
<p>Рабочая PostgreSQL недоступна, поэтому проверка выполнена на отдельной SQLite-базе. Бизнес-логика, модели, маршруты и JavaScript приложения не изменены. Шаблоны заявок на согласование сейчас не подключены к маршрутам: их заголовки приведены к общей системе в коде, но не представлены как проверенные страницы.</p>
<details><summary>Повторить проверку</summary><p><code>python -m tools.seed_visual</code><br><code>python manage.py runserver 127.0.0.1:8765 --settings=tools.visual_settings --noreload</code><br><code>python tools/capture_visual.py final</code><br><code>python tools/build_visual_report.py</code><br>Для скриншотов требуется Playwright и Chromium. При изменении шаблонов сервер с <code>--noreload</code> нужно перезапустить.</p></details></section>
<h2>Скриншоты</h2><p>Поиск по странице или состоянию: users, contracts, payments, expenses, refunds, imports, history, form, errors, mobile, laptop, narrow, wide, scroll.</p><p><input id="filter" type="search" placeholder="Фильтр скриншотов" aria-label="Фильтр скриншотов"></p><div class="gallery">CARDS</div></main>
<script>document.querySelector('#filter').addEventListener('input',e=>{const q=e.target.value.toLowerCase().trim();document.querySelectorAll('article').forEach(a=>a.hidden=!a.dataset.name.includes(q))})</script></html>'''
(out / 'index.html').write_text(report.replace('SCREENS', str(len(data['pages']))).replace('CARDS', ''.join(cards)), encoding='utf-8')
print(out / 'index.html')
