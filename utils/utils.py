import pandas as pd
from unidecode import unidecode
from datetime import datetime
from pytz import timezone

mexico_tz = 'America/Mexico_City'

def get_dates_dataframe(start='2024-03-01'):
    today = datetime.now(tz=timezone(mexico_tz))
    all_dates = pd.DataFrame({'date':pd.date_range(start,today.strftime('%Y-%m-%d'))})
    return all_dates


def custom_read(csv_path=None, excel_path=None, excel_tab_name=None):
    if csv_path:
        res = pd.read_csv(csv_path)
    else:
        assert excel_path is not None, "csv_path o excel_path deben especificarse"
        assert excel_tab_name  is not None, "especifica el nombre de pestaña"
        res = pd.read_excel(excel_path,sheet_name=excel_tab_name)
    return res



def last_column_with_one(row):
    # Reverse the order of columns to find the last occurrence
    for col in reversed(row.index[1:]):  # Skip the 'id' column
        if row[col] == 1:
            return col
    return None  # Return None if no column has value 1


def process_columns(df):
    """lowercase replace white spaces with _"""
    df1 = df.copy()
    cols = [
        unidecode(
            c.strip()
            .lower()
            .replace(" ", "_")
            .replace(".", "")
            .replace(":", "")
            .replace("_/_", "_")
        )
        for c in df1.columns
    ]
    df1.columns = cols
    return df1


def millions_formatter(x, pos):
    """formats numbers as millions
    """
    return f'{x / 1e6:.1f}M'  # Format as X.XM


def add_year_week(df, date_column="date"):
    """adds []'year', 'week', 'year_week', 'monday_of_week'] columns to a dataframe containing the column 'date'
    """
     
    new_df = df.assign(
        year=lambda x: x.date.dt.year,
        week=lambda x: x.date.dt.isocalendar().week,
        year_week=lambda x: x.year.astype(str) + "-" + x.week.astype(str),
        monday_of_week=lambda x: (
            x.date - pd.to_timedelta(x.date.dt.dayofweek, unit="d")
        ).dt.strftime("%Y-%m-%d"),
                    )
    new_df['sunday_of_week'] = (new_df['date'] - 
        pd.to_timedelta(df['date'].dt.weekday + 1, unit='d'))

    new_df['sunday_of_week'] = (new_df
                                .apply(
        lambda row: row['date'] if row['date'].weekday(
        ) == 6 else row['sunday_of_week'],
        axis=1
            )
            )
    return new_df

def remove_accents(text):
    if isinstance(text, str):
        return unidecode(text)
    return text             

