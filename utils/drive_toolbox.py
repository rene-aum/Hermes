from datetime import datetime
import pandas as pd
import pytz
from gspread_dataframe import set_with_dataframe,get_as_dataframe
import io
import time
from googleapiclient.discovery import build
import re
import requests
import json


def from_drive_to_local(drive, id_file, file_name):
    """moves file from google drive to current local directory
       drive: GoogleDrive object
       id_file: id of the drive file
       file_name: name of the file to use in the local directory
    """
    links = drive.CreateFile({'id':id_file})
    links.GetContentFile(file_name)
    return

def get_last_modification_date_drive(drive,sheet_id):
    id_ = sheet_id
    link = drive.CreateFile({'id':id_})
    timestamp_utc=link.GetRevisions()[-1].get('modifiedDate')
    dt_utc = datetime.fromisoformat(timestamp_utc.replace('Z', '+00:00'))
    mexico_city_tz = pytz.timezone('America/Mexico_City')
    dt_mexico_city = dt_utc.astimezone(mexico_city_tz)
    formatted_timestamp = dt_mexico_city.strftime('%Y-%m-%d %H:%M:%S %Z%z')
    data_date = pd.to_datetime(formatted_timestamp).strftime('%Y-%m-%d')
    return data_date

def create_sheets_in_drive_folder(gc,file_name,folder_id,df_to_set=None):

    spreadsheet = gc.create(file_name, folder_id=folder_id)
    # spreadsheet.share('user@example.com', perm_type='user', role='writer') # Optional: share

    worksheet = spreadsheet.sheet1
    if df_to_set is not None:
        set_with_dataframe(worksheet, df_to_set)
    print(f"Google Sheet {file_name} created and updated in folder ID: {folder_id}")

def update_sheets_in_drive_folder(
        gc,
        spreadsheet_id,
        worksheet_name,
        df_to_update,
        retries: int = 3,
        initial_delay: float = 2.0,
        backoff_factor: float = 2.0,
        ):
    """
    Update a Google Sheets worksheet with a DataFrame, retrying on failure.

    Parameters
    ----------
    gc : gspread.Client
        Authenticated gspread client.
    spreadsheet_id : str
        ID of the Google Sheet.
    worksheet_name : str
        Name of the worksheet to update.
    df_to_update : pandas.DataFrame
        DataFrame whose contents will replace the worksheet.
    retries : int, default 3
        Number of attempts in total (initial try + retries-1).
    initial_delay : float, default 2.0
        Seconds to sleep before the first retry.
    backoff_factor : float, default 2.0
        Multiplier applied to the delay after each failed attempt.
    """

    attempt = 0
    delay = initial_delay
    last_exception = None

    while attempt < retries:
        attempt += 1
        try:
            # 1. Open the existing spreadsheet by ID
            spreadsheet = gc.open_by_key(spreadsheet_id)

            # 2. Access the worksheet by name
            worksheet = spreadsheet.worksheet(worksheet_name)

            # 3. Clear the existing content of the worksheet
            worksheet.clear()

            # 4. Update the worksheet with the DataFrame
            set_with_dataframe(worksheet, df_to_update)

            print(
                f"[attempt {attempt}/{retries}] "
                f"Google Sheet {spreadsheet_id!r} - {worksheet_name!r} "
                f"updated with new data."
            )
            return  # success → exit the function

        except Exception as e:
            last_exception = e
            print(
                f"[attempt {attempt}/{retries}] "
                f"Failed to update sheet {spreadsheet_id!r} - {worksheet_name!r}: {e}"
            )

            if attempt >= retries:
                # no more retries left: re-raise or handle as you prefer
                print("Exhausted all retries; giving up.")
                raise

            # wait before the next retry
            print(f"Retrying in {delay} seconds...")
            time.sleep(delay)
            delay *= backoff_factor

def read_from_google_sheets(gc,spreadsheet_id,sheetname=None):
    """
    """

    # Open the Google Sheet using the extracted ID
    spreadsheet = gc.open_by_key(spreadsheet_id)
    if sheetname is  None:
        worksheet = spreadsheet.sheet1  # Or select a specific worksheet
    else:
        worksheet = spreadsheet.worksheet(sheetname)
    # Read the data into a pandas DataFrame
    df = get_as_dataframe(worksheet,
                          evaluate_formulas=True,
                        value_render_option="UNFORMATTED_VALUE")

    return df

def list_file_ids_for_drive_folder(drive, folder_id:str):
    file_list = drive.ListFile({'q': f"'{folder_id}' in parents and trashed=false"}).GetList()
    file_id_dict = {}
    for file in file_list:
        file_id_dict[file['title']] = file['id']
    return file_id_dict

def read_csv_from_drive(drive,file_id,**read_csv_kwargs):
    """
    """
    file = drive.CreateFile({'id': file_id})
    csv_bytes = file.GetContentString()  # returns CSV as a text string

    # --- Load into pandas ---
    df = pd.read_csv(io.StringIO(csv_bytes),**read_csv_kwargs)
    return df

def write_csv_to_drive(drive,file_id, df):
    """Ya debe existir el archivo csv en drive y por tanto el file_id
        df: pandas dataframe
    """
    # Convert to CSV
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    
    csv_content = csv_buffer.getvalue()

    # Añadir BOM para que Excel detecte correctamente UTF-8
    if encoding and encoding.lower().replace("_", "-") == "utf-8-sig":
        csv_content = "\ufeff" + csv_content

    file = drive.CreateFile({"id": file_id})
    file.SetContentString(csv_content)
    file.Upload()

def create_csv_file_in_drive_folder(drive,folder_id,df,filename):
    """filename: string with extension .csv
    """
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)
    csv_str = csv_buffer.getvalue()
    file_metadata = {
                    "title": filename,   # what the user sees in Drive
                    "mimeType": "text/csv",
                    "parents": [{"id": folder_id}] 
                        }
    file = drive.CreateFile(file_metadata)
    file.SetContentString(csv_str)  # upload from string
    file.Upload()
    print("Uploaded file ID:", file["id"])
    return file["id"]

def list_permissions(creds,file_id):
    drive_service = build("drive", "v3", credentials=creds)
    permissions = (drive_service.permissions().list(
                    fileId=file_id,
                    fields="permissions(id,emailAddress,role,type,domain)"
                            ).execute())
    resdf = pd.DataFrame(permissions['permissions'])
    return resdf

def remove_write_permissions_sheets(gc,sheet_id,email_user_list):
  """remove permissions for a list of emails, downgrades writer to reader.
     removes complete permissions then assigns reader permissions
  """
  # update permission
  spreadsheet = gc.open_by_key(sheet_id)
  # share with an email as writer
  for u in email_user_list:
    print(u)
    spreadsheet.remove_permissions(u, role='writer')
    print(spreadsheet.share(u, perm_type='user', role='reader', notify=False))

  return

def share_write_permissions_sheets(gc,sheet_id,email_user_list):
  """
  Docstring para share_write_permissions_sheets
  
  :param gc: Descripción
  :param sheet_id: Descripción
  :param email_user_list: Descripción
  """
  # update permission
  spreadsheet = gc.open_by_key(sheet_id)
  # share with an email as writer
  for u in email_user_list:
    print(u)
    print(spreadsheet.share(u, perm_type='user', role='writer', notify=False))
  return

def _a1_to_rowcol(a1: str):
    """
    Minimal A1 parser for a cell like 'B2' -> (row=2, col=2).
    """
    m = re.fullmatch(r"\s*([A-Za-z]+)(\d+)\s*", a1)
    if not m:
        raise ValueError(f"Invalid A1 cell reference: {a1!r}")
    col_letters, row_str = m.group(1).upper(), m.group(2)

    col = 0
    for ch in col_letters:
        col = col * 26 + (ord(ch) - ord("A") + 1)

    row = int(row_str)
    return row, col


def find_last_filled_row_in_sheet(
        gc,
        spreadsheet_id: str,
        worksheet_name: str = None,
        scan_col: int = 1,
        include_header: bool = True,
        ):
    """
    Find the last row index (1-based) that has *any* non-empty value in a given column.

    Parameters
    ----------
    gc : gspread.Client
        Authenticated gspread client.
    spreadsheet_id : str
        ID of the Google Sheet.
    worksheet_name : str, optional
        Worksheet name; if None uses sheet1.
    scan_col : int, default 1
        Column index (1-based) to scan for last non-empty row.
        Usually 1 (col A) if that column is always populated.
    include_header : bool, default True
        If False, treats row 1 as header and returns at least 1 even if only header exists.

    Returns
    -------
    int
        Last filled row (>=1). If sheet is empty and include_header=True -> 0,
        if include_header=False -> 1 (header row).
    """
    spreadsheet = gc.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.sheet1 if worksheet_name is None else spreadsheet.worksheet(worksheet_name)

    # Fetch the full column. This is typically efficient enough for most sheets.
    # If you have extremely large sheets, you can optimize with batch ranges later.
    col_values = worksheet.col_values(scan_col)

    # Normalize: treat whitespace-only strings as empty
    def _is_nonempty(x):
        if x is None:
            return False
        if isinstance(x, str) and x.strip() == "":
            return False
        return True

    last = 0
    for i, v in enumerate(col_values, start=1):
        if _is_nonempty(v):
            last = i

    if last == 0:
        return 0 if include_header else 1
    return last


def append_dataframe_to_google_sheet_from_range(
        gc,
        spreadsheet_id: str,
        worksheet_name: str,
        df_to_append: pd.DataFrame,
        start_cell: str = "A1",
        include_header: bool = False,
        scan_col: int = 1,
        retries: int = 3,
        initial_delay: float = 2.0,
        backoff_factor: float = 2.0,
        ):
    """
    Append a DataFrame to an existing worksheet starting at a specific column (from start_cell),
    but automatically chooses the row based on the last filled row (in scan_col).

    Behavior:
      - Parses `start_cell` (e.g., 'C2') to get the starting column.
      - Finds last filled row using `find_last_filled_row_in_sheet(...)`.
      - Writes df starting at:
            row = max(start_row_from_start_cell, last_filled_row + 1)
            col = start_col_from_start_cell

    Parameters
    ----------
    gc : gspread.Client
        Authenticated gspread client.
    spreadsheet_id : str
        ID of the Google Sheet.
    worksheet_name : str
        Worksheet name.
    df_to_append : pandas.DataFrame
        DataFrame to append.
    start_cell : str, default "A1"
        A1 cell that defines the starting column (and minimum row).
        Example: "C2" means append into column C, and never write above row 2.
    include_header : bool, default False
        Whether to write DataFrame column headers as the first row of the appended block.
    scan_col : int, default 1
        Column index (1-based) to determine "last filled row".
        Pick a column that is always filled for real rows.
    retries / initial_delay / backoff_factor
        Same retry style as your update function.

    Returns
    -------
    dict
        Metadata about the write location.
    """
    if df_to_append is None or len(df_to_append) == 0:
        print("Nothing to append: df_to_append is empty.")
        return {"written": False, "start_row": None, "start_col": None}

    min_row, start_col = _a1_to_rowcol(start_cell)

    attempt = 0
    delay = initial_delay
    last_exception = None

    while attempt < retries:
        attempt += 1
        try:
            spreadsheet = gc.open_by_key(spreadsheet_id)
            worksheet = spreadsheet.worksheet(worksheet_name)

            last_filled = find_last_filled_row_in_sheet(
                gc=gc,
                spreadsheet_id=spreadsheet_id,
                worksheet_name=worksheet_name,
                scan_col=scan_col,
                include_header=True,  # detect true emptiness
            )

            start_row = max(min_row, last_filled + 1)

            set_with_dataframe(
                worksheet,
                df_to_append,
                row=start_row,
                col=start_col,
                include_column_header=include_header,
                resize=False,  # don't shrink/expand the sheet automatically
            )

            print(
                f"[attempt {attempt}/{retries}] Appended df with shape={df_to_append.shape} "
                f"to {spreadsheet_id!r} - {worksheet_name!r} at {start_row=}, {start_col=}."
            )

            return {
                "written": True,
                "start_row": start_row,
                "start_col": start_col,
                "last_filled_row_before": last_filled,
                "include_header": include_header,
            }

        except Exception as e:
            last_exception = e
            print(
                f"[attempt {attempt}/{retries}] Failed to append to sheet "
                f"{spreadsheet_id!r} - {worksheet_name!r}: {e}"
            )
            if attempt >= retries:
                print("Exhausted all retries; giving up.")
                raise

            print(f"Retrying in {delay} seconds...")
            time.sleep(delay)
            delay *= backoff_factor


def send_google_chat_notification(webhook_url:str,msg:str):
    # TWebhook
    try:
        # Mensaje
        payload = {
            "text": f"*{msg}*"
        }

        # Realizar el envío
        response = requests.post(
            webhook_url,
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json; charset=UTF-8'}
        )

        if response.status_code == 200:
            print("Notificación enviada a Google Chat.")
        else:
            print(f"Error al enviar: {response.status_code}")

    except Exception as e:
        print(f"Error en la función: {e}")

