import pandas as pd

TIME_FEATURES_ORDERED = ('year', 'month', 'week')

def produce_dt_feature(df: pd.DataFrame, col: str, feature: str) -> pd.Series:
    if feature in ['year', 'month', 'day', 'hour', 'minute']:
        return getattr(df[col].dt, feature)
    elif feature == 'week':
        return df[col].dt.isocalendar().week 
    else:
        raise KeyError(f'cant produce feature series for key {feature}')
