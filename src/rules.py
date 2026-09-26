"""Exécute les règles SQL de surveillance sur une base SQLite en mémoire."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from config import PAYS_A_RISQUE, SEUIL_VIGILANCE

SQL = (Path(__file__).parent / "rules.sql").read_text(encoding="utf-8")


def charger_base(membres: pd.DataFrame, tx: pd.DataFrame) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    t = tx.copy()
    t["horodatage"] = pd.to_datetime(t["horodatage"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    t.to_sql("transactions", con, index=False)
    membres.to_sql("membres", con, index=False)
    pd.DataFrame({"code": PAYS_A_RISQUE}).to_sql("pays_risque", con, index=False)
    con.execute("CREATE INDEX ix_tx ON transactions(membre_id, horodatage)")
    return con


def executer_regles(con: sqlite3.Connection) -> pd.DataFrame:
    """Renvoie une ligne par (membre, règle) avec le détail le plus parlant."""
    brut = pd.read_sql_query(SQL, con, params={"seuil": SEUIL_VIGILANCE})
    brut.columns = ["membre_id", "regle", "nb_occurrences", "detail"]
    agg = (brut.sort_values("nb_occurrences", ascending=False)
               .groupby(["membre_id", "regle"], as_index=False)
               .agg(nb_occurrences=("nb_occurrences", "sum"), detail=("detail", "first")))
    return agg
