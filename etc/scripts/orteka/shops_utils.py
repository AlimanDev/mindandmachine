import pandas as pd
from src.base.models import Shop
from src.forecast.models import OperationType, OperationTypeName, PeriodClients
from src.timetable.models import WorkType, WorkTypeName


shop_types = [
        [
            '358-1', '364-1', '220-1', '277-1', '289-1', '348-1', '358-1',
            '364-1', '371-1', '216-1', '217-1', '237-1', '259-1', '278-1',
            '360-1', '361-1', '363-1'
        ],  # низкая конверсия
        [
            '141-1', '152-1', '167-1', '198-1', '204-1', '207-1', '208-1',
            '209-1', '211-1', '225-1', '226-1', '231-1', '247-1', '248-1',
            '252-1', '253-1', '258-1', '266-1', '269-1', '273-1', '274-1',
            '275-1', '276-1', '279-1', '295-1', '300-1', '302-1', '306-1',
            '310-1', '311-1', '315-1', '319-1', '321-1', '325-1', '335-1',
            '340-1', '346-1', '350-1', '369-1', '370-1', '372-1', '376-1',
            '378-1', '379-1', '380-1', '138-1', '145-1', '157-1', '158-1',
            '161-1', '166-1', '173-1', '175-1', '183-1', '185-1', '186-1',
            '188-1', '189-1', '190-1', '191-1', '192-1', '194-1', '195-1',
            '196-1', '201-1', '205-1', '206-1', '21-01', '212-1', '215-1',
            '219-1', '223-1', '227-1', '228-1', '230-1', '234-1', '235-1',
            '236-1', '244-1', '249-1', '254-1', '268-1', '270-1', '281-1',
            '282-1', '285-1', '288-1', '293-1', '294-1', '301-1', '314-1',
            '330-1', '334-1', '339-1', '344-1', '366-1', '375-1', '381-1',
            '7-001'
        ],  # средняя конверсия
        [
            '133-1', '137-1', '146-1', '15-02', '151-1', '154-1', '159-1',
            '163-1', '165-1', '17-01', '172-1', '178-1', '197-1', '199-1',
            '213-1', '222-1', '229-1', '239-1', '242-1', '243-1', '250-1',
            '260-1', '261-1', '265-1', '280-1', '296-1', '307-1', '31-01',
            '318-1', '329-1', '352-1', '357-1', '373-1', '377-1', '4-001',
            '1-001', '132-1', '134-1', '139-1', '143-1', '153-1', '160-1',
            '162-1', '177-1', '182-1', '184-1', '187-1', '193-1', '218-1',
            '22-01', '238-1', '246-1', '267-1', '28-02', '290-1', '3-001',
            '324-1', '351-1', '362-1', '9-001'
        ],  # высокая конверсия
    ]


def export_shops(to_file):
    data = []
    for shop in Shop.objects.all():
        data.append({
            'name': shop.name,
            'code': shop.code,
            'start_time': min(shop.open_times.values()),
            'end_time': max(shop.close_times.values()),
            'shop_type': 0 if shop.code in shop_types[0] else 1 if shop.code in shop_types[1] else 2
        })

    df = pd.DataFrame(data)
    df = df[['name', 'code', 'start_time', 'end_time', 'shop_type']]
    df['norm_coef'] = 1
    df.to_excel(to_file)
    return df


def add_operations_to_shops(exclude_shops):
    # во всех магазинах есть все операции  (работает, только если 1 сеть магазинов в базе !!!)
    operation_type_names = list(OperationTypeName.objects.all().select_related('work_type_name'))

    for shop in Shop.objects.all().exclude(id__in=exclude_shops):
        for opt in operation_type_names:
            wt = None
            if opt.work_type_name:
                wt, _ = WorkType.objects.get_or_create(
                    shop_id=shop.id,
                    work_type_name_id=opt.work_type_name.id,
                )
            OperationType.objects.get_or_create(
                shop=shop,
                operation_type_name=opt,
                work_type=wt,
            )


def import_workload2shops(filepath, serie_type=PeriodClients.LONG_FORECASE_TYPE, operation_names_dict=None):
    df = pd.read_csv(filepath, index_col=0, parse_dates=['dttm'])

    if not (('dttm' in df.columns) and ('shop_code' in df.columns)):
        raise ValueError(f'no dttm or shop_code in columns {df.columns}')

    if operation_names_dict:
        df = df.rename(columns=operation_names_dict)
        operation_names = operation_names_dict.values()
    else:
        operation_names = set(df.columns) - {'dttm', 'shop_code'}

    operation_type_names = list(OperationTypeName.objects.filter(name__in=operation_names).select_related('work_type_name'))

    if len(operation_type_names) != len(operation_names):
        print(f'mismatch: {operation_names} \nvs\n {operation_type_names}')

    for shop_code in df['shop_code'].unique():
        shop = list(Shop.objects.filter(code=shop_code))
        if len(shop) != 1:
            print(f'with shop_code {shop_code} return: {shop}')
        else:
            shop = shop[0]
            shop_workload = df[df['shop_code'] == shop_code]

            dttm_min = shop_workload.dttm.min()
            dttm_max = shop_workload.dttm.max()

            for opt in operation_type_names:
                wt = None
                if opt.work_type_name:
                    wt, _ = WorkType.objects.get_or_create(
                        shop_id=shop.id,
                        work_type_name_id=opt.work_type_name.id,
                    )
                operation_type, _ = OperationType.objects.get_or_create(
                    shop=shop,
                    operation_type_name=opt,
                    work_type=wt,
                )

                PeriodClients.objects.filter(
                    dttm_forecast__gte=dttm_min,
                    dttm_forecast__lte=dttm_max,
                    operation_type=operation_type,
                    type=serie_type
                ).delete()

                PeriodClients.objects.bulk_create([
                    PeriodClients(
                        dttm_forecast=row['dttm'],
                        operation_type=operation_type,
                        type=serie_type,
                        value=row[opt.name]

                    ) for _, row in shop_workload[['dttm', opt.name]].iterrows()
                ])

