"""Reusable historico update pipeline.

This module extracts the logic from ``nb0_update_historico.ipynb`` into a
single callable so it can be imported from notebooks or other Python code.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import pytz


# Make sure the repository root is importable no matter where the notebook runs.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from utils.drive_toolbox import (  # noqa: E402
    create_csv_file_in_drive_folder,
    list_file_ids_for_drive_folder,
    read_csv_from_drive,
    read_from_google_sheets,
    write_csv_to_drive,
)


DEFAULT_HISTORICO_FOLDER_ID = "1zvW-Dxow9gz1Dnbpg_jO7my4wadDvJDW"
DEFAULT_HISTORICO_FILE_ID = "1EVBy847HLGatCkN8pNqbb44pe_ULEBCS"
DEFAULT_TORRE_V2_SHEET_ID = "1k8rguLeF1O33XCaVDxPiQ1C4SbxLDSIeqNcriYtsF-k"
DEFAULT_TORRE_V2_SHEET_NAME = "asignacion"
DEFAULT_LATEST_FILENAME = "historico_tc_latest.csv"
DEFAULT_CERRADOS = ["CERRADO", "COMPRA EXITOSA", "COMPRA EXITOSA "]
DEFAULT_TZ = "America/Mexico_City"


def _now_str(tz_name: str) -> str:
    return datetime.now(tz=pytz.timezone(tz_name)).strftime("%Y-%m-%d %H:%M:%S")


def _today_stamp(tz_name: str) -> str:
    return datetime.now(tz=pytz.timezone(tz_name)).strftime("%Y-%m-%d %H:%M")


def _bootstrap_drive_clients() -> Tuple[Any, Any]:
    """Bootstrap Google Drive and gspread clients in Colab."""
    try:
        from google.colab import auth
        from oauth2client.client import GoogleCredentials
        from pydrive2.auth import GoogleAuth
        from pydrive2.drive import GoogleDrive
        from google.auth import default
        import gspread
    except Exception as exc:  # pragma: no cover - environment specific
        raise RuntimeError(
            "Could not bootstrap Google Drive clients. "
            "Pass `drive` and `gc` explicitly or run in Colab with the "
            "required packages installed."
        ) from exc

    auth.authenticate_user()
    gauth = GoogleAuth()
    gauth.credentials = GoogleCredentials.get_application_default()
    drive = GoogleDrive(gauth)

    creds, _ = default()
    gc = gspread.authorize(creds)
    return drive, gc


def _update_from_torre_v2(
    historico: pd.DataFrame,
    asig_torre_v2: pd.DataFrame,
    now_str: str,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    subset_columns_v2 = [
        "id lead",
        "origen automarket",
        "cosecha",
        "id comprador",
        "folio bauto tc",
        "nombre comprador",
        "mail comprador",
        "telefono comprador",
        "asesor credito",
        "espacio automarket",
        "asesor espacio",
        "fecha de asignacion",
        "estatus de lead",
        "fecha de reactivacion credito",
        "fecha de reactivacion eam",
    ]

    nueva_torre_append = (
        asig_torre_v2[subset_columns_v2]
        .merge(historico[["id lead"]], on=["id lead"], how="left", indicator=True)
        [lambda x: x["_merge"] == "left_only"]
        .drop(columns=["_merge"])
        .assign(flag_torre_v2=1, fecha_de_proceso=now_str)
    )

    update_df_torre_v2_cerr = (
        historico[lambda x: x["estatus de lead"].isin(DEFAULT_CERRADOS)]
        .merge(
            asig_torre_v2[
                ["id lead", "estatus de lead", "asesor espacio", "asesor credito", "espacio automarket"]
            ],
            on="id lead",
            how="left",
            suffixes=("", " tcv2"),
            indicator=True,
        )
        [lambda x: x["_merge"] == "both"]
        .drop(columns=["_merge"])
        [lambda x: (x["estatus de lead tcv2"].notna()) & (
            (x["estatus de lead"].str.strip() != x["estatus de lead tcv2"].str.strip())
        )]
        .assign(flag_torre_v2=1, fecha_de_proceso=now_str)
    )
    update_df_torre_v2_cerr["flag salio de cerrado"] = pd.NA
    mask_salio_cerrado = (
        (update_df_torre_v2_cerr["estatus de lead"] == "CERRADO")
        & (update_df_torre_v2_cerr["estatus de lead tcv2"] != "CERRADO")
    )
    update_df_torre_v2_cerr.loc[mask_salio_cerrado, "flag salio de cerrado"] = 1
    # update_df_torre_v2_cerr["espacio automarket"] = update_df_torre_v2_cerr["espacio automarket tcv2"]
    # update_df_torre_v2_cerr["asesor espacio"] = update_df_torre_v2_cerr["asesor espacio tcv2"]
    # update_df_torre_v2_cerr["asesor credito"] = update_df_torre_v2_cerr["asesor credito tcv2"]
    update_df_torre_v2_cerr["estatus de lead"] = update_df_torre_v2_cerr["estatus de lead tcv2"]

    
    update_df_torre_v2_cerr = update_df_torre_v2_cerr.drop(
        columns=["estatus de lead tcv2", "asesor espacio tcv2", "espacio automarket tcv2", "asesor credito tcv2"]
    )

    update_df_torre_v2_open = (
        historico[lambda x: ~x["estatus de lead"].isin(DEFAULT_CERRADOS)]
        .merge(
            asig_torre_v2[
                ["id lead", "estatus de lead", "asesor espacio", "asesor credito", "espacio automarket"]
            ],
            on="id lead",
            how="left",
            suffixes=("", " tcv2"),
            indicator=True,
        )
        [lambda x: x["_merge"] == "both"]
        .drop(columns=["_merge"])
        [lambda x: (x["estatus de lead tcv2"].notna()) & (
            (x["estatus de lead"].str.strip() != x["estatus de lead tcv2"].str.strip())
            | (x["espacio automarket"].str.strip() != x["espacio automarket tcv2"].str.strip())
            | (x["asesor espacio"].str.strip() != x["asesor espacio tcv2"].str.strip())
        )]
        .assign(flag_torre_v2=1, fecha_de_proceso=now_str)
    )
    update_df_torre_v2_open["espacio automarket"] = update_df_torre_v2_open["espacio automarket tcv2"]
    update_df_torre_v2_open["asesor espacio"] = update_df_torre_v2_open["asesor espacio tcv2"]
    update_df_torre_v2_open["asesor credito"] = update_df_torre_v2_open["asesor credito tcv2"]
    update_df_torre_v2_open["estatus de lead"] = update_df_torre_v2_open["estatus de lead tcv2"]
    update_df_torre_v2_open = update_df_torre_v2_open.drop(
        columns=["estatus de lead tcv2", "asesor espacio tcv2", "espacio automarket tcv2", "asesor credito tcv2"]
    )

    df_no_update_tc_v2 = (
        historico
        .merge(update_df_torre_v2_open[["id lead"]], on=["id lead"], how="left", indicator=True)
        [lambda x: x["_merge"] == "left_only"]
        .drop(columns=["_merge"])
        .merge(update_df_torre_v2_cerr[["id lead"]], on=["id lead"], how="left", indicator=True)
        [lambda x: x["_merge"] == "left_only"]
        .drop(columns=["_merge"])
    )

    resultado_final = (
        pd.concat(
            [df_no_update_tc_v2, nueva_torre_append, update_df_torre_v2_open, update_df_torre_v2_cerr]
        )
        .reset_index(drop=True)
    )

    return resultado_final, nueva_torre_append, update_df_torre_v2_open, update_df_torre_v2_cerr


def actualizar_historico_leads(
    drive: Optional[Any] = None,
    gc: Optional[Any] = None,
    *,
    from_drive: bool = True,
    historico_folder_id: str = DEFAULT_HISTORICO_FOLDER_ID,
    historico_file_id: str = DEFAULT_HISTORICO_FILE_ID,
    torre_v2_sheet_id: str = DEFAULT_TORRE_V2_SHEET_ID,
    torre_v2_sheet_name: str = DEFAULT_TORRE_V2_SHEET_NAME,
    latest_filename: str = DEFAULT_LATEST_FILENAME,
    write_outputs: bool = True,
    create_timestamped_copy: bool = True,
    tz_name: str = DEFAULT_TZ,
    verbose: bool = True,
    return_details: bool = False,
) -> Any:
    """Run the full historico update pipeline.

    Parameters
    ----------
    drive, gc:
        Authenticated Google Drive / gspread clients. If either is missing and
        ``from_drive`` is ``True``, the function will try to bootstrap them in
        a Colab-like environment.
    write_outputs:
        If ``True``, overwrite the latest CSV file in Drive.
    create_timestamped_copy:
        If ``True``, also create a dated CSV copy in the Drive folder.
    return_details:
        If ``True``, return a dictionary with the intermediate dataframes in
        addition to the final result.
    """
    if drive is None or gc is None:
        if not from_drive:
            raise ValueError("Provide both `drive` and `gc` when `from_drive=False`.")
        drive, gc = _bootstrap_drive_clients()

    today = _today_stamp(tz_name)
    now_str = _now_str(tz_name)

    dicc_historico = list_file_ids_for_drive_folder(drive, historico_folder_id)
    historico = read_csv_from_drive(drive, historico_file_id)
    cols_borrar = historico.filter(like="reactivacion").columns.values.tolist()
    historico = historico.drop(columns=cols_borrar)

    if verbose:
        print(f"shape historico: {historico.shape[0]}")
        print(f"Leads unicos en historico: {historico['id lead'].nunique()}")

    asig_torre_v2 = read_from_google_sheets(gc, torre_v2_sheet_id, sheetname=torre_v2_sheet_name)
    asig_torre_v2["fecha de asignacion"] = pd.to_datetime(
        asig_torre_v2["fecha de asignacion"], format="%d/%m/%Y", errors="coerce"
    ).dt.strftime("%Y-%m-%d")

    if verbose:
        print(f"shape torre v2: {asig_torre_v2.shape[0]}. leads unicos torre v2: {asig_torre_v2['id lead'].nunique()}")

    assert asig_torre_v2.shape[0] == asig_torre_v2["id lead"].nunique(), "Leads duplicados en torre v2"

    resultado_final, nueva_torre_append, update_df_torre_v2_open, update_df_torre_v2_cerr = _update_from_torre_v2(
        historico, asig_torre_v2, now_str
    )

    if verbose:
        print(f"Filas a anadir de tc v2: {nueva_torre_append.shape[0]}")
        print(f"Filas a actualizar de tc v2 leads cerrados: {update_df_torre_v2_cerr.shape[0]}")
        print(f"Filas a actualizar de tc v2 leads abiertos: {update_df_torre_v2_open.shape[0]}")
        print(resultado_final.shape[0], resultado_final["id lead"].nunique())

    assert resultado_final.shape[0] == historico.shape[0] + nueva_torre_append.shape[0]

    output_file_id = dicc_historico[latest_filename]
    timestamped_filename = f"historico_tc_{today}.csv"

    if create_timestamped_copy:
        create_csv_file_in_drive_folder(drive, historico_folder_id, resultado_final, timestamped_filename)
        print(f'Copia del historico timestamp... OK')
    if write_outputs:
        write_csv_to_drive(drive, output_file_id, resultado_final)
        print(f'Escritura del historico... OK')

    result: Dict[str, Any] = {
        "resultado_final": resultado_final,
        "historico": historico,
        "asig_torre_v2": asig_torre_v2,
        "nueva_torre_append": nueva_torre_append,
        "update_df_torre_v2_open": update_df_torre_v2_open,
        "update_df_torre_v2_cerr": update_df_torre_v2_cerr,
        "output_file_id": output_file_id,
        "latest_filename": latest_filename,
        "timestamped_filename": timestamped_filename,
        "historico_folder_id": historico_folder_id,
    }

    return result if return_details else resultado_final
