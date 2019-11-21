import json
import pandas as pd


def get_predict_cashiers(path1, path2):
    f = open(path1)
    data = json.load(f)
    f.close()

    elems = []
    for elem in data['data']['forecast_periods']['L']:
        elems.append({
            'dttm': elem['dttm'],
            'predict': elem['B']
        })
    pred = pd.DataFrame(elems)

    f = open(path2)
    data = json.load(f)
    f.close()

    cashiers = pd.DataFrame(data['data']['tt_periods']['real_cashiers'])
    res = pd.merge(pred, cashiers, on='dttm')
    return res
