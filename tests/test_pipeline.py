import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evaluate import evaluer  # noqa: E402
from generate_data import Generateur  # noqa: E402
from ml import calculer_indicateurs, scorer_anomalies  # noqa: E402
from rules import charger_base, executer_regles  # noqa: E402
from scoring import construire_alertes  # noqa: E402


def test_pipeline_detecte_la_majorite_des_cas():
    membres, tx = Generateur(seed=7).run(n_membres=300)
    regles = executer_regles(charger_base(membres, tx))
    alertes = construire_alertes(membres, regles, scorer_anomalies(calculer_indicateurs(membres, tx)))
    res = evaluer(alertes, membres)
    assert res["rappel"] >= 0.7
    assert res["precision"] >= 0.4
    assert alertes.score_risque.between(0, 100).all()


def test_regle_pays_a_risque():
    membres, tx = Generateur(seed=1).run(n_membres=50)
    tx.loc[0, "pays_contrepartie"] = "KP"
    regles = executer_regles(charger_base(membres, tx))
    assert ((regles.regle == "R3_PAYS_A_RISQUE") & (regles.membre_id == tx.loc[0, "membre_id"])).any()
