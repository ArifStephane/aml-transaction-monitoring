"""Interface analyste : tableau de bord, file d'alertes, dossier membre et
qualification tracée des alertes.  Lancer : streamlit run app.py"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE / "src"))
from evaluate import evaluer  # noqa: E402
from run_pipeline import executer  # noqa: E402

FICHIER_DECISIONS = RACINE / "output" / "decisions_analyste.csv"
DECISIONS = ["Classée sans suite (justifiée)", "Demande de justificatifs au membre",
             "Mesure conservatoire (gel / blocage)", "Déclaration de soupçon TRACFIN à étudier"]

st.set_page_config(page_title="Surveillance LCB-FT", page_icon="🔎", layout="wide")


@st.cache_data
def charger():
    if not (RACINE / "data" / "transactions.csv").exists():
        from generate_data import Generateur
        m, t = Generateur().run()
        (RACINE / "data").mkdir(exist_ok=True)
        m.to_csv(RACINE / "data" / "membres.csv", index=False)
        t.to_csv(RACINE / "data" / "transactions.csv", index=False)
    alertes, _ = executer()
    membres = pd.read_csv(RACINE / "data" / "membres.csv")
    tx = pd.read_csv(RACINE / "data" / "transactions.csv", parse_dates=["horodatage"])
    return alertes, membres, tx


def lire_decisions() -> pd.DataFrame:
    if FICHIER_DECISIONS.exists():
        return pd.read_csv(FICHIER_DECISIONS)
    return pd.DataFrame(columns=["horodatage", "analyste", "membre_id", "score_risque", "decision", "justification"])


alertes, membres, tx = charger()
file_alertes = alertes[alertes.alerte].copy()

st.title("🔎 Surveillance des transactions LCB-FT")
st.caption("Démonstrateur sur données 100 % fictives — règles SQL + détection d'anomalies (Isolation Forest)")

onglets = st.tabs(["Tableau de bord", "File d'alertes", "Dossier membre", "Performance du dispositif"])

# ------------------------------------------------------------------ dashboard
with onglets[0]:
    dec = lire_decisions()
    c = st.columns(5)
    c[0].metric("Transactions analysées", f"{len(tx):,}".replace(",", " "))
    c[1].metric("Membres surveillés", len(membres))
    c[2].metric("Alertes ouvertes", int(len(file_alertes) - dec.membre_id.nunique()))
    c[3].metric("Priorité haute", int((file_alertes.priorite == "HAUTE").sum()))
    c[4].metric("Alertes qualifiées", int(dec.membre_id.nunique()))

    g1, g2 = st.columns(2)
    regles = file_alertes.regles_declenchees.fillna("").str.split(", ").explode()
    regles = regles[regles != ""].value_counts().rename_axis("regle").reset_index(name="nb")
    g1.plotly_chart(px.bar(regles, x="nb", y="regle", orientation="h", title="Règles déclenchées (membres en alerte)",
                           color_discrete_sequence=["#2c3e50"]),
                    use_container_width=True)
    g2.plotly_chart(px.histogram(alertes, x="score_risque", color="priorite", nbins=40,
                                 title="Distribution des scores de risque (échelle log)", log_y=True,
                                 color_discrete_map={"HAUTE": "#c0392b", "MOYENNE": "#e67e22", "AUCUNE": "#95a5a6"},
                                 category_orders={"priorite": ["HAUTE", "MOYENNE", "AUCUNE"]}), use_container_width=True)

# ------------------------------------------------------------------ file d'alertes
with onglets[1]:
    f1, f2 = st.columns(2)
    prio = f1.multiselect("Priorité", ["HAUTE", "MOYENNE"], default=["HAUTE", "MOYENNE"])
    typ = f2.multiselect("Type de membre", ["PARTICULIER", "PRO"], default=["PARTICULIER", "PRO"])
    vue = file_alertes[file_alertes.priorite.isin(prio) & file_alertes.type_membre.isin(typ)]
    st.dataframe(vue[["membre_id", "score_risque", "priorite", "type_membre", "niveau_risque_kyc",
                      "regles_declenchees", "indicateurs_atypiques"]],
                 use_container_width=True, hide_index=True)
    st.download_button("Exporter la file (CSV)", vue.to_csv(index=False).encode("utf-8"), "file_alertes.csv")

# ------------------------------------------------------------------ dossier
with onglets[2]:
    mid = st.selectbox("Membre", file_alertes.membre_id.tolist())
    a = alertes.set_index("membre_id").loc[mid]
    p = membres.set_index("membre_id").loc[mid]
    c = st.columns(4)
    c[0].metric("Score de risque", int(a.score_risque))
    c[1].metric("Priorité", str(a.priorite))
    c[2].metric("Revenu / CA mensuel déclaré", f"{p.revenu_mensuel_declare:,.0f} €".replace(",", " "))
    c[3].metric("Risque KYC", p.niveau_risque_kyc)
    st.markdown("**Motifs de l'alerte**")
    for motif in str(a.motifs).split(" | "):
        if motif and motif != "nan":
            st.markdown(f"- {motif}")
    st.markdown(f"- Indicateurs les plus atypiques (ML) : {a.indicateurs_atypiques} "
                f"(score d'anomalie {a.score_anomalie:.2f})")

    t = tx[tx.membre_id == mid].copy()
    t["montant_signe"] = t.montant.where(t.sens == "IN", -t.montant)
    st.plotly_chart(px.scatter(t, x="horodatage", y="montant_signe", color="canal", hover_data=["pays_contrepartie", "contrepartie_id"],
                               title="Flux du membre (entrées > 0, sorties < 0)"), use_container_width=True)
    with st.expander("Transactions (hors paiements carte)"):
        st.dataframe(t[t.canal != "CARTE"].drop(columns=["typologie_injectee", "montant_signe"]), hide_index=True)

    st.markdown("**Qualification de l'alerte** — chaque décision est horodatée et tracée")
    with st.form("qualif"):
        analyste = st.text_input("Analyste")
        decision = st.radio("Décision", DECISIONS)
        justif = st.text_area("Justification (obligatoire)")
        if st.form_submit_button("Enregistrer la décision"):
            if not analyste or not justif.strip():
                st.error("L'analyste et la justification sont obligatoires.")
            else:
                d = lire_decisions()
                ligne = pd.DataFrame([{"horodatage": datetime.now().isoformat(timespec="seconds"), "analyste": analyste,
                                        "membre_id": mid, "score_risque": int(a.score_risque),
                                        "decision": decision, "justification": justif.strip()}])
                pd.concat([d, ligne]).to_csv(FICHIER_DECISIONS, index=False)
                st.success("Décision enregistrée dans le journal d'audit.")
    hist = lire_decisions()
    hist = hist[hist.membre_id == mid]
    if len(hist):
        st.dataframe(hist, hide_index=True)

# ------------------------------------------------------------------ performance
with onglets[3]:
    st.info("Les données étant fictives, les comportements suspects injectés sont connus : on peut donc mesurer "
            "la précision (part des alertes justifiées) et le rappel (part des cas suspects détectés).")
    res = evaluer(alertes, membres)
    c = st.columns(4)
    c[0].metric("Précision", f"{res['precision']:.0%}")
    c[1].metric("Rappel", f"{res['rappel']:.0%}")
    c[2].metric("Faux positifs", res["faux_positifs"])
    c[3].metric("Cas manqués", res["faux_negatifs"])
    st.dataframe(res["par_typologie"], hide_index=True)
