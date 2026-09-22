"""Fase 3.5 -- Exploração interativa dos resultados de clustering (V1/V2).

Dashboard local (Streamlit) pra visualizar onde cada faixa fica posicionada nos
modelos de clustering já treinados, escolher quais features projetar nos eixos, e
filtrar por gênero/MyTag/artista/faixa/BPM/rating. Ponte entre "rodamos o
clustering" (Fase 3) e a próxima fase de classificação de faixas: antes de propor
regras de classificação, dá pra olhar onde as faixas caem hoje e questionar
visualmente se os clusters fazem sentido musical (ver achado V1 x V2 no README).

Rodar: streamlit run src/explorer.py

Reaproveita a lógica de features de cluster_v1.py/cluster_v2.py (mesmo espaço de
features usado pra treinar os modelos) em vez de duplicá-la -- os eixos "PCA 1"/
"PCA 2"/"PCA 3" são a mesma família de projeção usada nos PNGs estáticos de
reports/ (só que com 1 componente a mais), e os clusters mostrados são os labels
já persistidos em track_clusters (não recalculados aqui).

Gráfico em 3D (Scatter3d): a interação de rotação do Plotly (arrastar pra orbitar)
é o que justifica 3D aqui -- um scatter 3D estático teria oclusão e perspectiva
distorcendo distância, mas dentro do Streamlit a rotação é nativa e gratuita.
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sklearn.decomposition import PCA
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cluster_v1  # noqa: E402
import cluster_v2  # noqa: E402
from clustering_common import get_engine  # noqa: E402

# Paleta categórica validada (skill dataviz/references/palette.md), ordem fixa --
# nunca ciclada. Com k=4 em ambos os modelos, o par all-pairs (todo par visível ao
# mesmo tempo, caso de scatter) falha o piso de CVD só com cor -- validado com
# scripts/validate_palette.js do skill dataviz -- então cada cluster também ganha
# um símbolo distinto como codificação secundária.
CATEGORICAL_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
# Scatter3d só aceita um enum de símbolos menor que o Scatter 2D (sem
# triangle-up/star/etc.) -- lista própria pra 3D, mesma ordem fixa.
CATEGORICAL_SYMBOLS = ["circle", "square", "diamond", "cross", "x", "circle-open", "diamond-open", "square-open"]
OTHER_COLOR = "#898781"

st.set_page_config(page_title="Beat Insights — Explorador de Clusters", layout="wide")


@st.cache_data(show_spinner="Carregando faixas e MyTag da base...")
def load_base():
    engine = get_engine()
    # Colunas extras (name/artist/key_camelot/play_count) além das que
    # cluster_v1.load_data traz -- essa tela precisa delas pra exibir, o
    # clustering em si não usa. build_features ignora as colunas extras.
    tracks = pd.read_sql("SELECT track_id, name, artist, key_camelot, bpm, genre, rating, play_count FROM tracks", engine)
    mytag_long = pd.read_sql(
        "SELECT tm.track_id, mv.value_name FROM track_mytag tm JOIN mytag_values mv ON mv.value_id = tm.value_id",
        engine,
    )
    mytag_by_track = mytag_long.groupby("track_id")["value_name"].apply(lambda s: sorted(set(s))).to_dict()
    return tracks, mytag_long, mytag_by_track


@st.cache_data(show_spinner="Montando espaço de features V1 (metadados)...")
def load_v1():
    engine = get_engine()
    tracks, mytag_long, mytag_by_track = load_base()
    features = cluster_v1.build_features(tracks, mytag_long)
    labels = pd.read_sql(
        text("SELECT track_id, cluster_label FROM track_clusters WHERE cluster_version = 'v1_structured'"), engine
    ).set_index("track_id")["cluster_label"]

    df = tracks.set_index("track_id").loc[features.index].copy()
    df["cluster"] = labels.loc[features.index]
    coords = PCA(n_components=3, random_state=42).fit_transform(features)
    df["pca_1"], df["pca_2"], df["pca_3"] = coords[:, 0], coords[:, 1], coords[:, 2]
    df["mytags"] = df.index.map(lambda tid: ", ".join(mytag_by_track.get(tid, [])) or "—")
    return df.reset_index()


@st.cache_data(show_spinner="Montando espaço de features V2 (metadados + áudio)...")
def load_v2():
    engine = get_engine()
    tracks, mytag_long, mytag_by_track = load_base()
    audio = cluster_v2.load_audio_features(engine)
    features = cluster_v2.build_features(tracks, mytag_long, audio)
    labels = pd.read_sql(
        text("SELECT track_id, cluster_label FROM track_clusters WHERE cluster_version = 'v2_audio'"), engine
    ).set_index("track_id")["cluster_label"]

    df = tracks.set_index("track_id").loc[features.index].copy()
    df["cluster"] = labels.loc[features.index]
    coords = PCA(n_components=3, random_state=42).fit_transform(features)
    df["pca_1"], df["pca_2"], df["pca_3"] = coords[:, 0], coords[:, 1], coords[:, 2]

    audio_indexed = audio.set_index("track_id").loc[features.index]
    for col in ["tempo_detected", "spectral_centroid_mean", "rms_energy_mean"]:
        df[col] = audio_indexed[col]
    df["mytags"] = df.index.map(lambda tid: ", ".join(mytag_by_track.get(tid, [])) or "—")
    return df.reset_index()


st.title("Explorador de Clusters")
st.caption(
    "Fase 3.5 — visualização interativa dos modelos de clustering antes de definir regras de "
    "classificação de faixas. Os clusters aqui são os mesmos persistidos em `track_clusters` "
    "(Fase 3), não recalculados nesta tela."
)

version = st.sidebar.radio("Versão do modelo", ["V1 — metadados estruturados", "V2 — metadados + áudio"])
df = load_v1() if version.startswith("V1") else load_v2()

if version.startswith("V1"):
    st.info(
        "**V1**: k-means só com BPM, rating, gênero e MyTag (one-hot). k=4, silhouette 0.368. "
        "Achado: o cluster dominante (61% da base) parece separar mais por *ausência de rating/MyTag* "
        "do que por semelhança sonora — ver README, seção \"Resultados obtidos\".",
        icon="ℹ️",
    )
else:
    st.info(
        "**V2**: metadados + features de áudio via `librosa` (tempo, spectral centroid, RMS, MFCCs, "
        "chroma). k=4, mas silhouette caiu para 0.072 e o Adjusted Rand Index contra o V1 é 0.019 — "
        "os dois modelos discordam quase totalmente sobre o que é \"parecido\". Ver README.",
        icon="ℹ️",
    )

axis_options = {
    "PCA 1": "pca_1",
    "PCA 2": "pca_2",
    "PCA 3": "pca_3",
    "BPM": "bpm",
    "Rating": "rating",
    "Play Count": "play_count",
}
if version.startswith("V2"):
    axis_options.update(
        {
            "Tempo detectado (áudio)": "tempo_detected",
            "Spectral centroid (áudio)": "spectral_centroid_mean",
            "RMS energy (áudio)": "rms_energy_mean",
        }
    )

st.sidebar.divider()
st.sidebar.subheader("Eixos do gráfico (3D)")
axis_labels = list(axis_options)
x_label = st.sidebar.selectbox("Eixo X", axis_labels, index=0)
y_label = st.sidebar.selectbox("Eixo Y", axis_labels, index=1)
z_label = st.sidebar.selectbox("Eixo Z", axis_labels, index=2)

st.sidebar.divider()
st.sidebar.subheader("Filtros")

genres = sorted(df["genre"].dropna().unique())
selected_genres = st.sidebar.multiselect("Gênero", genres)

all_tags = sorted({t for tags in df["mytags"] for t in (tags.split(", ") if tags != "—" else [])})
selected_tags = st.sidebar.multiselect("MyTag", all_tags)

artist_query = st.sidebar.text_input("Artista contém")
name_query = st.sidebar.text_input("Faixa contém")

bpm_lo, bpm_hi = float(df["bpm"].min()), float(df["bpm"].max())
bpm_range = st.sidebar.slider("BPM", bpm_lo, bpm_hi, (bpm_lo, bpm_hi))
rating_range = st.sidebar.slider("Rating", 0, 5, (0, 5))

filtered = df
if selected_genres:
    filtered = filtered[filtered["genre"].isin(selected_genres)]
if selected_tags:
    filtered = filtered[filtered["mytags"].apply(lambda tags: any(t in tags.split(", ") for t in selected_tags))]
if artist_query:
    filtered = filtered[filtered["artist"].str.contains(artist_query, case=False, na=False)]
if name_query:
    filtered = filtered[filtered["name"].str.contains(name_query, case=False, na=False)]
filtered = filtered[filtered["bpm"].between(*bpm_range) & filtered["rating"].between(*rating_range)]

st.sidebar.caption(f"{len(filtered)} de {len(df)} faixas após os filtros")

clusters = sorted(filtered["cluster"].unique())
if len(clusters) > len(CATEGORICAL_COLORS):
    st.warning(
        f"{len(clusters)} clusters visíveis — acima do que a paleta categórica valida com segurança "
        f"({len(CATEGORICAL_COLORS)}); clusters extras aparecem em cinza."
    )
color_map = {c: (CATEGORICAL_COLORS[i] if i < len(CATEGORICAL_COLORS) else OTHER_COLOR) for i, c in enumerate(clusters)}
symbol_map = {c: CATEGORICAL_SYMBOLS[i % len(CATEGORICAL_SYMBOLS)] for i, c in enumerate(clusters)}

fig = go.Figure()
hover_cols = ["name", "artist", "genre", "key_camelot", "bpm", "rating", "play_count", "mytags"]
for c in clusters:
    sub = filtered[filtered["cluster"] == c]
    fig.add_trace(
        go.Scatter3d(
            x=sub[axis_options[x_label]],
            y=sub[axis_options[y_label]],
            z=sub[axis_options[z_label]],
            mode="markers",
            name=f"Cluster {c}",
            marker=dict(color=color_map[c], symbol=symbol_map[c], size=4, line=dict(width=0.5, color="#fcfcfb")),
            customdata=sub[hover_cols],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>%{customdata[1]}<br>"
                "Gênero: %{customdata[2]}<br>Key: %{customdata[3]} · BPM: %{customdata[4]}<br>"
                "Rating: %{customdata[5]} · Plays: %{customdata[6]}<br>"
                "MyTag: %{customdata[7]}<extra></extra>"
            ),
        )
    )
axis_style = dict(gridcolor="#e1e0d9", zerolinecolor="#c3c2b7", backgroundcolor="#fcfcfb")
fig.update_layout(
    scene=dict(
        xaxis=dict(title=x_label, **axis_style),
        yaxis=dict(title=y_label, **axis_style),
        zaxis=dict(title=z_label, **axis_style),
        bgcolor="#fcfcfb",
    ),
    legend_title="Cluster",
    paper_bgcolor="#fcfcfb",
    font=dict(color="#0b0b0b", family="system-ui, -apple-system, 'Segoe UI', sans-serif"),
    height=700,
    margin=dict(t=20, l=0, r=0, b=0),
)
st.plotly_chart(fig, use_container_width=True)
st.caption("Arraste pra rotacionar, role pra dar zoom, clique nos itens da legenda pra isolar um cluster.")

st.subheader("Perfil dos clusters (faixas filtradas)")
if filtered.empty:
    st.warning("Nenhuma faixa atende aos filtros atuais.")
else:
    summary = (
        filtered.groupby("cluster")
        .agg(
            faixas=("track_id", "size"),
            bpm_medio=("bpm", "mean"),
            rating_medio=("rating", "mean"),
            genero_mais_comum=("genre", lambda s: s.mode().iat[0] if not s.mode().empty else None),
        )
        .round(1)
    )
    st.dataframe(summary, use_container_width=True)

with st.expander(f"Ver as {len(filtered)} faixas filtradas como tabela"):
    st.dataframe(
        filtered[["track_id", "name", "artist", "genre", "key_camelot", "bpm", "rating", "play_count", "cluster", "mytags"]]
        .sort_values(["cluster", "name"]),
        use_container_width=True,
        hide_index=True,
    )
