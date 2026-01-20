from datetime import datetime
import pandas as pd
import pytz
from gspread_dataframe import set_with_dataframe,get_as_dataframe
import io
import time



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

def read_csv_from_drive(drive,file_id):
    """
    """
    file = drive.CreateFile({'id': file_id})
    csv_bytes = file.GetContentString()  # returns CSV as a text string

    # --- Load into pandas ---
    df = pd.read_csv(io.StringIO(csv_bytes))
    return df

def write_csv_to_drive(drive,file_id, df):
    """Ya debe existir el archivo csv en drive y por tanto el file_id
        df: pandas dataframe
    """
    # Convert to CSV
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)

    # Load existing Drive file by ID
    file = drive.CreateFile({"id": file_id})
    file.SetContentString(csv_buffer.getvalue())
    file.Upload()    # <-- overwrites content, keeps same file ID

    print("Updated successfully.")

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
