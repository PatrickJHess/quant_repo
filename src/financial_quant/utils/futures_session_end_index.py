import pandas as pd

def futures_session_end_index(df: pd.DataFrame, sort: bool = True, drop: bool = True) -> pd.DataFrame:
    """
    Reindexes a Massive futures DataFrame by 'session_end_date' as a DatetimeIndex
    without mutating the original DataFrame.
    """
    if 'session_end_date' not in df.columns:
        print("🚫 No 'session_end_date' column found. Returning unmodified copy.")
        return df.copy()

    x = df.copy()
    x['session_end_date'] = pd.to_datetime(x['session_end_date'])
    x.set_index('session_end_date', drop=drop, inplace=True)

    if sort:
        x.sort_index(inplace=True)

    return x
