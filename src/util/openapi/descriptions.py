SHOP_UPDATE = '''
Необходимо перенести и поддерживать актуальную информацию
 по управленческой структуре подразделений (территориям) 
 и информации о подразделениях. На основе управленческой 
 структуры подразделений строятся ролевая модель доступа сотрудников и отчетность.\n
'''

RECIEPT = '''
Расчет потребности в персонале строится на основе исторических данных по бизнес драйверам. Бизнес драйверы представляются в виде временных рядов. Есть 2 метода как можно передать бизнес драйвер:\n
1. В виде количества/суммы событий за период
2. В виде произошедших событий (данные сагрегируются на стороне WFM по определенным правилам в количество/сумму событий за период)\n
Ключевые поля:\n
1. Идентификатор события
2. Время события (формат времени "2020-07-20T11:00:00.000Z")
3. Код подразделения
4. Значение (по необходимости, если надо суммировать)
'''

WORKER_DAY_LIST = '''
Для автоматизации расчета заработной платы по факту отработанного времени необходимо забирать данные из системы.\n
**Пример:**\n
/rest_api​/worker_day​/?worker__username__in=12345,123,345&is_tabel=true&dt__gte=2020-08-18&dt__lte=2020-09-17&by_code=true\n
Из ответа нужны будут поля:\n
1. worker_username
2. shop_code
3. dttm_work_start (дата и время начала работы)
4. dttm_work_end (дата и время конца работы)
5. dt (дата дня – избыточная информация, но удобная если есть ночные смены)
6. work_hours_details – количество отработанного времени с указанием деталей рабочего времени (D – дневное время, N – ночное время)
7. type (тип дня – выходной, отпуск, рабочий день).\n
**Перечень типов работ:**\n
|Название|Описание|Обозначение|
|:------------:|:------------:|:------------:|
|Явка, Ночные часы|Рабочий день сотрудника. В work_hours_details сколько дневных (D) и ночных часов  (N)|W|
|Праздники|Работа в праздники. В work_hours_details статус H|W|
|Командировка|период выгрузки от даты (включительно)|T|
|Отпуск|период выгрузки до даты (включительно)|V|
|Отпуск по беременности и родам|Подтвержденную ли версию вернуть (только подтвержденная нужна)|M|
|Отпуск по уходу за ребенком|Код магазина (если хотим по определенному магазину посмотреть график). Поле не обязательное, если есть worker__username__in|MC|
|Доп. отпуск без сохранения заработной платы|Отпуск за свой счет|TV|
|Больничный||S|
|Прогул||RA|
|Неявки по невыясненным причинам||A|
|Выходной||H|
|Повышение квалификации / обучение|Повышение квалификации / обучение|Q|
'''
