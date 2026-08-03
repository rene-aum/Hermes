"""Generación de reportes de clientes y pedidos desde AWS.

Este módulo adapta fielmente la lógica del notebook
`extraccionPedidosClientesDL.ipynb` para poder llamarla desde otros notebooks.

Las instalaciones de paquetes, la autenticación de Colab, el montaje de Drive
y la creación del objeto ``AWSToolbox`` deben realizarse en el notebook
orquestador, no dentro de este archivo.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

import boto3
import numpy as np
import pandas as pd


BUCKET_NAME = "aws-s3-reporte-atenea-usorg-nprd"
SILVER_PATH = "data/Silver"

DEFAULT_CLIENTES_DRIVE_CSV_ID = "1yGZ2u7F74a-sIScI3puoF_Vy9t9Vl90w"
DEFAULT_PEDIDOS_DRIVE_FOLDER_ID = "1fttKxZMGSrgW8HJBcRyfczgOPcRu6twi"


def actualizar_reporte_clientes(
    ah: Any,
    drive: Any,
    write_csv_to_drive: Any,
    drive_folder_id: str = DEFAULT_CLIENTES_DRIVE_CSV_ID,
    nombre_archivo: str = "prueba_clientes.csv",
) -> pd.DataFrame:
    """Extrae, transforma y guarda el reporte de clientes.

    Parameters
    ----------
    ah:
        Instancia autenticada de ``automarket_utils.aws.AWSToolbox``.
    drive:
        Instancia autenticada de Google Drive utilizada por la función helper.
    write_csv_to_drive:
        Función ``utils.drive_toolbox.write_csv_to_drive``.
    drive_folder_id:
        ID de la carpeta de Drive en la que se creará el CSV.
    nombre_archivo:
        Nombre del archivo CSV que se guardará en Drive.

    Returns
    -------
    pandas.DataFrame
        DataFrame final con la misma estructura del notebook original.
    """
    bucket = f"{ah.bucket}/{SILVER_PATH}"
    base = f"{bucket}/Commerce/reporteClientes"

    cltescm = ah.read_latest_partition(base)
    cltescm["Id. de la cuenta"] = ""
    cltescm["Nombre de la cuenta"] = cltescm["customer_preferred_name"].apply(
        lambda x: x if " " not in x else x.split(" ")[0]
    )

    cols_cltescm = [
        "Id. de la cuenta",
        "customer_since",
        "customer_id_commerce",
        "customer_preferred_name",
        "Nombre de la cuenta",
        "customer_phone",
        "customer_email_address",
        "customer_date_of_birth",
    ]
    cltescm = cltescm[cols_cltescm]

    cltescm["customer_since"] = pd.to_datetime(
        cltescm["customer_since"]
    ).dt.strftime("%d/%m/%Y")
    cltescm["customer_date_of_birth"] = pd.to_datetime(
        cltescm["customer_date_of_birth"]
    ).dt.strftime("%d/%m/%Y")
    cltescm["customer_phone"] = cltescm["customer_phone"].astype(str).str.strip()
    cltescm["customer_email_address"] = (
        cltescm["customer_email_address"].astype(str).str.strip()
    )

    cltescm.columns = [
        "Id. de la cuenta",
        "Fecha de creación",
        "Id Comercio Externo",
        "Contacto principal",
        "Nombre de la cuenta",
        "Teléfono",
        "Email",
        "Fecha de nacimiento",
    ]

    write_csv_to_drive(
        drive,
        DEFAULT_CLIENTES_DRIVE_CSV_ID,
        cltescm
    )

    return cltescm


def actualizar_reporte_pedidos(
    ah: Any,
    drive: Any,
    create_csv_file_in_drive_folder: Any,
    drive_folder_id: str = DEFAULT_PEDIDOS_DRIVE_FOLDER_ID,
    nombre_archivo: Optional[str] = None,
    guardar_copia_local: bool = False,
    ruta_copia_local: str = "pddssf.csv",
    s3_client: Any = None,
) -> pd.DataFrame:
    """Extrae, transforma y guarda el reporte de pedidos.

    La transformación conserva el orden y las reglas del notebook original,
    incluido el encabezado de ocho filas y la fila de total.

    Parameters
    ----------
    ah:
        Instancia autenticada de ``automarket_utils.aws.AWSToolbox``.
    drive:
        Instancia autenticada de Google Drive utilizada por la función helper.
    create_csv_file_in_drive_folder:
        Función ``utils.drive_toolbox.create_csv_file_in_drive_folder``.
    drive_folder_id:
        ID de la carpeta de Drive en la que se creará el CSV.
    nombre_archivo:
        Nombre del CSV. Si no se proporciona, se genera a partir del corte.
    guardar_copia_local:
        Si es ``True``, también escribe el CSV en el entorno local.
    ruta_copia_local:
        Ruta de la copia local.
    s3_client:
        Cliente boto3 opcional. Si no se proporciona, se crea uno con
        ``boto3.client('s3')``.

    Returns
    -------
    pandas.DataFrame
        DataFrame final con la misma estructura del notebook original.
    """
    bucket = f"{ah.bucket}/{SILVER_PATH}"

    # Publicaciones: se obtiene el espacio asociado a cada SKU.
    base_publicaciones = f"{bucket}/Atlas/ProcPublicaciones"
    pbcs = ah.read_latest_partition(base_publicaciones)
    pbcs = pbcs[["sku", "showroom"]]
    pbcs["showroom"] = (
        pbcs["showroom"]
        .str.replace("Metrópoli ", "", regex=False)
        .replace("Reforma 510", "Torre BBVA")
        .replace("", np.nan)
    )
    pbcs = pbcs.set_index("sku")["showroom"].to_dict()

    # Pedidos: casteos y columnas faltantes.
    base_pedidos = f"{bucket}/Salesforce/informePedidos"
    pddssf = ah.read_latest_partition(base_pedidos)
    pddssf["order_id"] = (
        pd.to_numeric(pddssf["order_id"], errors="coerce")
        .astype("Int64")
        .astype(str)
        .str.zfill(8)
    )
    pddssf["dummy"] = np.nan
    pddssf["order_amount"] = "MXN" + pddssf["order_amount"].map(
        lambda x: f"{x:,.2f}"
    )
    pddssf["created_date"] = pd.to_datetime(pddssf["created_date"]).dt.strftime(
        "%d/%m/%Y"
    )

    # Se conserva el bfill del notebook original.
    pddssf["Dirección del Espacio en Pedido"] = (
        pddssf["sku"].map(pbcs).bfill().str.replace("é", "e", regex=False)
    )

    sel_cols_pddssf = (
        ["dummy"]
        + list(pddssf.columns[:1])
        + ["dummy"]
        + list(pddssf.columns[1:15])
        + ["Dirección del Espacio en Pedido", "sku"]
    )
    pddssf = pddssf[sel_cols_pddssf]

    pddssf.columns = [
        "",
        "Número de pedido",
        " ",
        "Pedido: Id comercio externo",
        "Id. de la cuenta",
        "Nombre de la cuenta",
        "Vendedor: Id Comercio Externo",
        "Comprador: Nombre de la cuenta",
        "Comprador: Id Comercio Externo",
        "Estado",
        "Precio de Publicación",
        "Fecha de creación",
        "Anticipo / Enganche",
        "Estatus",
        "Activo: Producto: Nombre del producto",
        "Activo: Vehículo Id: Número de Identificación Vehicular (NIV)",
        "Descripción",
        "Dirección del Espacio en Pedido",
        "SKU de Produto",
    ]

    # Fecha de corte del parquet.
    ultima_particion = ah.latest_partition_path(base_pedidos)
    prefix = "/".join(ultima_particion.split("/")[1:])
    s3 = s3_client or boto3.client("s3")
    response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix)
    corte_parquet = response.get("Contents", [])[0]["LastModified"].astimezone(
        ZoneInfo("America/Mexico_City")
    )
    corte_parquet = corte_parquet.strftime("%Y-%m-%d %H:%M:%S")

    # Encabezado homologado al reporte descargado de Salesforce.
    filas_vacias = pd.DataFrame(columns=pddssf.columns, index=range(8), data=[])
    etiquetas = [
        "Moises Reporte de Pedidos y producto +",
        (
            f"Actualización de parquet: {corte_parquet} Horario CDMX - "
            "Generado por Moises Eduardo Jimenez Hidalgo"
        ),
        "",
        "",
        "Sin filtro",
        f"{ultima_particion}",
        "",
        "",
    ]
    filas_vacias["Número de pedido"] = etiquetas

    fila_total = pd.DataFrame(columns=pddssf.columns, index=range(1), data=[])
    fila_total["Número de pedido"] = "Total"
    fila_total[" "] = "Conteo"
    fila_total["Pedido: Id comercio externo"] = pddssf[
        "Número de pedido"
    ].nunique()

    pddssf = pd.concat([filas_vacias, pddssf, fila_total]).reset_index(drop=True)
    pddssf["dummy"] = np.nan

    cols_pddssf = [
        np.nan,
        "Número de pedido",
        np.nan,
        "Pedido: Id comercio externo",
        "Id. de la cuenta",
        "Nombre de la cuenta",
        "Vendedor: Id Comercio Externo",
        "Comprador: Nombre de la cuenta",
        "Comprador: Id Comercio Externo",
        "Estado",
        "Precio de Publicación",
        "Fecha de creación",
        "Anticipo / Enganche",
        "Estatus",
        "Activo: Producto: Nombre del producto",
        "Activo: Vehículo Id: Número de Identificación Vehicular (NIV)",
        "Descripción",
        "Dirección del Espacio en Pedido",
        "SKU de Produto",
        np.nan,
    ]
    pddssf.iloc[7] = cols_pddssf
    pddssf.columns = [""] * len(pddssf.columns)

    if guardar_copia_local:
        pddssf.to_csv(ruta_copia_local, index=False, encoding="utf-8-sig")

    ahora = datetime.strptime(corte_parquet, "%Y-%m-%d %H:%M:%S")
    if nombre_archivo is None:
        nombre_archivo = ahora.strftime("pedidos_%Y-%m-%d-%H_%M%S.csv")

    create_csv_file_in_drive_folder(
        drive,
        drive_folder_id,
        pddssf,
        nombre_archivo,
    )

    return pddssf
