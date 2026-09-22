"""Dashboard local (Streamlit) com duas abas:

1. "Clusters" (Fase 3.5) -- visualiza os modelos de clustering V1/V2/V3
   (meta/meta_audio/audio) já treinados, com PCA 3D, filtros por gênero/MyTag/
   artista/faixa/BPM/rating. Ponte entre "rodamos o clustering" e a próxima fase
   de classificação de faixas: antes de propor regras, dá pra olhar onde as
   faixas caem hoje e questionar visualmente se os clusters fazem sentido
   musical (ver achado V1 x V2/V3 no README).

2. "Vizinhos" (Etapa 4 da fase "3 espaços + k-NN", ver ADR-001) -- busca de
   faixas parecidas via k-NN (src/similarity.py), com projeção 2D de fundo
   (UMAP por padrão, PCA como opção) mostrando a faixa de referência, os k
   vizinhos retornados e o resto da biblioteca em cinza claro.

Rodar: streamlit run src/explorer.py

Reaproveita a lógica de features de src/features.py e a busca de
src/similarity.py em vez de duplicá-las -- os clusters mostrados na aba 1 são
os labels já persistidos em track_clusters (não recalculados aqui); os vizinhos
da aba 2 vêm de similarity.similar_tracks, a mesma função usada pelo assistente
de LLM (Etapa 5).
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import umap
from sklearn.decomposition import PCA
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cluster_v1  # noqa: E402
import cluster_v2  # noqa: E402
import cluster_v3  # noqa: E402
import features as features_mod  # noqa: E402
import set_assistant  # noqa: E402
import similarity as similarity_mod  # noqa: E402
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
CHART_FONT = dict(color="#0b0b0b", family="system-ui, -apple-system, 'Segoe UI', sans-serif")

st.set_page_config(page_title="Beat Insights — Explorador", layout="wide")


# ---------------------------------------------------------------- dados: base

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


def classified_track_ids(tracks: pd.DataFrame, mytag_by_track: dict) -> frozenset:
    """Track_ids com rating > 0 OU MyTag atribuído -- mesmo critério de
    sql/queries/01_faixas_sem_classificacao.sql (lá, a negação: sem rating E
    sem MyTag). Compartilhado pelas abas Clusters e Vizinhos pro filtro "só
    tracks classificadas", pra não divergir a definição entre as duas."""
    return frozenset(
        tracks.loc[(tracks["rating"] > 0) | tracks["track_id"].isin(mytag_by_track.keys()), "track_id"]
    )


# ------------------------------------------------------- dados: aba Clusters

@st.cache_data(show_spinner="Montando espaço de features V1 (metadados)...")
def load_v1(restrict_ids: frozenset | None = None):
    """`restrict_ids`, quando informado, restringe tracks ao subconjunto antes
    de montar a matriz de features e troca a cluster_version lida pra
    'v1_structured_classified' (persistida por src/cluster_classified.py) --
    são clusters de fato recalculados nesse subconjunto, não um filtro visual
    em cima dos labels 'v1_structured' (base inteira)."""
    engine = get_engine()
    tracks, mytag_long, mytag_by_track = load_base()
    if restrict_ids is not None:
        tracks = tracks[tracks["track_id"].isin(restrict_ids)]
    features = cluster_v1.build_features(tracks, mytag_long)
    version = "v1_structured_classified" if restrict_ids is not None else "v1_structured"
    labels = pd.read_sql(
        text("SELECT track_id, cluster_label FROM track_clusters WHERE cluster_version = :v"),
        engine, params={"v": version},
    ).set_index("track_id")["cluster_label"]

    df = tracks.set_index("track_id").loc[features.index].copy()
    df["cluster"] = labels.loc[features.index]
    coords = PCA(n_components=3, random_state=42).fit_transform(features)
    df["pca_1"], df["pca_2"], df["pca_3"] = coords[:, 0], coords[:, 1], coords[:, 2]
    df["mytags"] = df.index.map(lambda tid: ", ".join(mytag_by_track.get(tid, [])) or "—")
    return df.reset_index()


@st.cache_data(show_spinner="Montando espaço de features V2 (metadados + áudio)...")
def load_v2(restrict_ids: frozenset | None = None):
    """Ver docstring de load_v1 -- mesmo esquema, cluster_version
    'v2_audio_classified' quando restrito."""
    engine = get_engine()
    tracks, mytag_long, mytag_by_track = load_base()
    audio = cluster_v2.load_audio_features(engine)
    if restrict_ids is not None:
        tracks = tracks[tracks["track_id"].isin(restrict_ids)]
        audio = audio[audio["track_id"].isin(restrict_ids)]
    features = cluster_v2.build_features(tracks, mytag_long, audio)
    version = "v2_audio_classified" if restrict_ids is not None else "v2_audio"
    labels = pd.read_sql(
        text("SELECT track_id, cluster_label FROM track_clusters WHERE cluster_version = :v"),
        engine, params={"v": version},
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


@st.cache_data(show_spinner="Montando espaço de features V3 (só áudio)...")
def load_v3(restrict_ids: frozenset | None = None):
    """Ver docstring de load_v1 -- mesmo esquema, cluster_version
    'v3_audio_only_classified' quando restrito."""
    engine = get_engine()
    tracks, mytag_long, mytag_by_track = load_base()
    audio = cluster_v2.load_audio_features(engine)
    if restrict_ids is not None:
        tracks = tracks[tracks["track_id"].isin(restrict_ids)]
        audio = audio[audio["track_id"].isin(restrict_ids)]
    features = cluster_v3.build_features(audio)
    version = "v3_audio_only_classified" if restrict_ids is not None else "v3_audio_only"
    labels = pd.read_sql(
        text("SELECT track_id, cluster_label FROM track_clusters WHERE cluster_version = :v"),
        engine, params={"v": version},
    ).set_index("track_id")["cluster_label"]

    # tracks não usa as colunas de áudio como feature aqui (V3 é só-áudio), mas
    # continuam disponíveis pra exibir/filtrar (bpm, rating, gênero, mytag).
    df = tracks.set_index("track_id").loc[features.index].copy()
    df["cluster"] = labels.loc[features.index]
    coords = PCA(n_components=3, random_state=42).fit_transform(features)
    df["pca_1"], df["pca_2"], df["pca_3"] = coords[:, 0], coords[:, 1], coords[:, 2]

    audio_indexed = audio.set_index("track_id").loc[features.index]
    for col in ["tempo_detected", "spectral_centroid_mean", "rms_energy_mean"]:
        df[col] = audio_indexed[col]
    df["mytags"] = df.index.map(lambda tid: ", ".join(mytag_by_track.get(tid, [])) or "—")
    return df.reset_index()


# ------------------------------------------------------- dados: aba Vizinhos

# Dimensões interpretáveis usadas no gráfico de comparação de perfil -- nomes
# de coluna na matriz padronizada de cada espaço (build_meta_audio prefixa
# colunas de áudio com "audio_", build_audio não, porque já é só áudio).
COMPARISON_DIMS = {
    "meta": [("bpm_scaled", "BPM"), ("rating_scaled", "Rating")],
    "meta_audio": [
        ("audio_tempo_detected", "Tempo (áudio)"),
        ("audio_spectral_centroid_mean", "Brilho (centroid)"),
        ("audio_rms_energy_mean", "Energia (RMS)"),
    ],
    "audio": [
        ("tempo_detected", "Tempo (áudio)"),
        ("spectral_centroid_mean", "Brilho (centroid)"),
        ("rms_energy_mean", "Energia (RMS)"),
    ],
}


@st.cache_data(show_spinner="Montando espaço e projeções (UMAP + PCA)...")
def load_space_for_knn(space: str, restrict_ids: frozenset | None = None):
    """Features padronizadas do espaço + projeções PCA e UMAP (2D) de fundo,
    pra plotar a biblioteca (ou um subconjunto dela) na aba Vizinhos. UMAP com
    random_state fixo (reprodutível) -- n_jobs=1 é exigido pelo umap-learn
    quando random_state é passado (senão ele ignora o paralelismo com um
    aviso).

    `restrict_ids`, quando informado, restringe tracks e audio ANTES de montar
    a matriz de features -- projeções e distâncias saem recalculadas dentro do
    subconjunto (não é um filtro visual em cima do resultado da base inteira).
    Usado pelo controle "Faixas incluídas na análise" (todas vs. só
    classificadas) na sidebar."""
    engine = get_engine()
    tracks = features_mod.load_tracks(engine)
    mytag = features_mod.load_mytag(engine)
    audio = features_mod.load_audio(engine)
    if restrict_ids is not None:
        tracks = tracks[tracks.track_id.isin(restrict_ids)]
        audio = audio[audio.track_id.isin(restrict_ids)]
    features = features_mod.build_space(space, tracks, mytag, audio)

    pca_coords = PCA(n_components=2, random_state=42).fit_transform(features)
    # n_neighbors não pode passar de (n amostras - 1) -- protege o caso de
    # escopo restrito reduzir bastante a base (ex.: só faixas classificadas).
    umap_n_neighbors = min(15, len(features) - 1)
    umap_coords = umap.UMAP(
        n_neighbors=umap_n_neighbors, min_dist=0.1, random_state=42, n_jobs=1
    ).fit_transform(features)

    display = pd.read_sql("SELECT track_id, name, artist, genre, key_camelot, bpm, rating FROM tracks", engine)
    df = display.set_index("track_id").loc[features.index].copy()
    df["pca_1"], df["pca_2"] = pca_coords[:, 0], pca_coords[:, 1]
    df["umap_1"], df["umap_2"] = umap_coords[:, 0], umap_coords[:, 1]
    return df.reset_index(), features


st.title("Explorador")

# ============================================================= chat flutuante
#
# Assistente de set (set_assistant.py, Fase 4 + Etapa 5) exposto como um
# popover fixado no canto da tela via CSS -- fica "pendente" (visível e
# clicável) em cima de qualquer view (Clusters ou Vizinhos), sem depender de
# qual delas está selecionada. Reaproveita set_assistant.run_turn/SYSTEM_PROMPT
# direto (mesmo tool calling do chat de terminal), não duplica a lógica.


def _message_role_and_content(msg):
    if isinstance(msg, dict):
        return msg.get("role"), msg.get("content")
    return msg.role, msg.content


if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = [{"role": "system", "content": set_assistant.SYSTEM_PROMPT}]

st.markdown(
    """
    <style>
    /* O botão do popover herda width:100% do container de bloco -- sem
    travar a largura aqui, position:fixed some com o layout normal mas o
    botão continua esticando pra largura da viewport inteira. */
    div[data-testid="stPopover"] {
        position: fixed;
        bottom: 1.5rem;
        right: 1.5rem;
        z-index: 999;
        width: fit-content;
    }
    div[data-testid="stPopover"] button {
        width: fit-content;
        border-radius: 999px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.25);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.popover("💬 Assistente de set", use_container_width=False):
    st.caption(f"Ollama local (`{set_assistant.MODEL}`) -- `query_library` + `similar_tracks` + `web_search`.")

    chat_box = st.container(height=380)
    with chat_box:
        for msg in st.session_state.chat_messages:
            role, content = _message_role_and_content(msg)
            if role in ("system", "tool") or not content:
                continue
            with st.chat_message("user" if role == "user" else "assistant"):
                st.write(content)

    user_msg = st.chat_input("Descreva o contexto do evento...", key="floating_chat_input")
    if user_msg:
        st.session_state.chat_messages.append({"role": "user", "content": user_msg})
        with st.spinner("Pensando..."):
            set_assistant.run_turn(get_engine(), st.session_state.chat_messages)
        st.rerun()

# ================================================================ navegação

# Seleção de visualização fica no menu lateral (não em abas) -- cada view
# mostra só os próprios controles no sidebar, não os das duas juntas.
view = st.sidebar.radio("Visualização", ["Clusters", "Vizinhos"], key="view_selector")
st.sidebar.divider()


# =============================================================== aba Clusters

if view == "Clusters":
    version = st.sidebar.radio(
        "Versão do modelo",
        ["V1 — metadados estruturados", "V2 — metadados + áudio", "V3 — só áudio (diagnóstico)"],
    )

    _tracks_base, _mytag_long_base, _mytag_by_track_base = load_base()
    cluster_classified_ids = classified_track_ids(_tracks_base, _mytag_by_track_base)

    cluster_scope = st.sidebar.radio(
        "Faixas incluídas na análise",
        ["Todas as tracks", "Só tracks classificadas"],
        key="cluster_scope",
        help=(
            "\"Classificada\" = rating > 0 ou com MyTag atribuído (mesmo critério de "
            "`sql/queries/01_faixas_sem_classificacao.sql`). Restringir usa clusters "
            "recalculados (k-means refeito só nesse subconjunto por "
            "`src/cluster_classified.py`, persistidos sob cluster_version própria) -- "
            "não é um filtro visual em cima dos clusters da base inteira."
        ),
    )
    cluster_restrict_ids = cluster_classified_ids if cluster_scope == "Só tracks classificadas" else None
    if cluster_restrict_ids is not None:
        st.sidebar.caption(
            f"{len(cluster_restrict_ids)} de {len(_tracks_base)} faixas classificadas "
            f"({len(cluster_restrict_ids) / len(_tracks_base):.0%}) — clustering recalculado "
            "só nesse subconjunto (ver `results/clustering_classificado_2026-09/summary.json`)."
        )

    loaders = {"V1": load_v1, "V2": load_v2, "V3": load_v3}
    df = loaders[version[:2]](cluster_restrict_ids)

    axis_options = {
        "PCA 1": "pca_1",
        "PCA 2": "pca_2",
        "PCA 3": "pca_3",
        "BPM": "bpm",
        "Rating": "rating",
        "Play Count": "play_count",
    }
    if not version.startswith("V1"):
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
    st.sidebar.subheader("Filtros (Clusters)")

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

    st.caption(
        "Fase 3.5 — visualização interativa dos modelos de clustering antes de definir regras de "
        "classificação de faixas. Os clusters aqui são os mesmos persistidos em `track_clusters` "
        "(Fase 3), não recalculados nesta tela."
    )

    if cluster_restrict_ids is None:
        if version.startswith("V1"):
            st.info(
                "**V1**: k-means só com BPM, rating, gênero e MyTag (one-hot). k=4, silhouette 0.368. "
                "Achado: o cluster dominante (61% da base) parece separar mais por *ausência de rating/MyTag* "
                "do que por semelhança sonora — ver README, seção \"Resultados obtidos\".",
                icon="ℹ️",
            )
        elif version.startswith("V2"):
            st.info(
                "**V2**: metadados + features de áudio via `librosa` (tempo, spectral centroid, RMS, MFCCs, "
                "chroma). k=4, mas silhouette caiu para 0.072 e o Adjusted Rand Index contra o V1 é 0.019 — "
                "os dois modelos discordam quase totalmente sobre o que é \"parecido\". Ver README.",
                icon="ℹ️",
            )
        else:
            st.info(
                "**V3**: k-means só com features de áudio (sem BPM/rating/gênero/MyTag na matriz) — "
                "diagnóstico pra isolar o sinal de áudio puro. k=4, silhouette 0.080. Achado: o Adjusted "
                "Rand Index contra o **V2 é 0.909** (quase idêntico) e contra o **V1 é 0.009** (quase "
                "aleatório) — o áudio domina quase totalmente o resultado do V2, o metadado contribui "
                "pouco. Ver README.",
                icon="ℹ️",
            )
    else:
        # Números reais de `src/cluster_classified.py`, rodado contra a biblioteca
        # (581/1649 faixas classificadas, 35%) -- ver
        # results/clustering_classificado_2026-09/summary.json.
        if version.startswith("V1"):
            st.info(
                "**V1, só classificadas**: mesmo espaço `meta`, k-means refeito só nas 581 faixas "
                "com rating > 0 ou MyTag (k=4). Silhouette **caiu pra 0.126** (vs. 0.368 na base inteira) "
                "e o Adjusted Rand Index contra o V1 completo é **0.0425** (quase nada em comum) — "
                "mas o cluster dominante de 61%/rating médio 0.0 *sumiu*: os 4 clusters agora ficam "
                "em 20–205 faixas, todos com rating médio entre 1.8 e 3.8. Confirma o achado original: "
                "o V1 completo estava separando sobretudo por *ter ou não* classificação, não por som.",
                icon="ℹ️",
            )
        elif version.startswith("V2"):
            st.info(
                "**V2, só classificadas**: k-means refeito só nas 580 faixas classificadas com áudio "
                "extraído (k=4). Silhouette **0.078** (vs. 0.072 na base inteira — praticamente igual) "
                "e Adjusted Rand Index contra o V2 completo é **0.41** — moderado, os clusters mudam "
                "mas não completamente. Diferente do V1, restringir a população não muda o quadro: "
                "o áudio já não estava sendo diluído pelo artefato de metadado ausente.",
                icon="ℹ️",
            )
        else:
            st.info(
                "**V3, só classificadas**: k-means refeito só nas 580 faixas classificadas com áudio "
                "extraído (k=4). Silhouette **0.101** (vs. 0.080 na base inteira — leve alta) e "
                "Adjusted Rand Index contra o V3 completo é **0.66** — o mais estável dos três frente "
                "à restrição, consistente com V3 já isolar o sinal de áudio puro, sem o metadado "
                "esparso que distorcia o V1. Ver `results/clustering_classificado_2026-09/summary.json`.",
                icon="ℹ️",
            )

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
        font=CHART_FONT,
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


# =============================================================== aba Vizinhos

else:  # view == "Vizinhos"
    tracks_base, _mytag_long, _mytag_by_track = load_base()
    track_label_to_id = {
        f"{row.name_} — {row.artist}" if row.artist else row.name_: row.track_id
        for row in tracks_base.rename(columns={"name": "name_"}).itertuples()
    }
    classified_ids = classified_track_ids(tracks_base, _mytag_by_track)

    st.sidebar.subheader("Vizinhos (k-NN)")
    knn_space = st.sidebar.selectbox("Espaço", ["meta", "meta_audio", "audio"], key="knn_space")

    knn_scope = st.sidebar.radio(
        "Faixas incluídas na análise",
        ["Todas as tracks", "Só tracks classificadas"],
        key="knn_scope",
        help=(
            "\"Classificada\" = rating > 0 ou com MyTag atribuído (mesmo critério de "
            "`sql/queries/01_faixas_sem_classificacao.sql`). Restringir recalcula "
            "vizinhança, projeção (PCA/UMAP) e comparação de perfil só dentro desse "
            "subconjunto -- não é um filtro visual sobre o resultado da base inteira."
        ),
    )
    restrict_ids = classified_ids if knn_scope == "Só tracks classificadas" else None
    if restrict_ids is not None:
        st.sidebar.caption(
            f"{len(restrict_ids)} de {len(tracks_base)} faixas classificadas "
            f"({len(restrict_ids) / len(tracks_base):.0%}) — dataset reduzido pra esta análise."
        )

    scoped_labels = sorted(
        lbl for lbl, tid in track_label_to_id.items() if restrict_ids is None or tid in restrict_ids
    )

    knn_search = st.sidebar.text_input("Buscar faixa por nome", key="knn_search")
    if knn_search:
        knn_options = [lbl for lbl in scoped_labels if knn_search.lower() in lbl.lower()]
        if not knn_options:
            st.sidebar.caption(f"Nenhuma faixa com {knn_search!r} no nome — mostrando a lista completa.")
            knn_options = scoped_labels
        else:
            st.sidebar.caption(f"{len(knn_options)} faixa(s) encontrada(s).")
    else:
        knn_options = scoped_labels

    if not knn_options:
        st.sidebar.error("Nenhuma faixa classificada disponível — desligue o filtro de escopo.")
        st.stop()

    knn_track_label = st.sidebar.selectbox("Faixa de referência", knn_options, key="knn_track")
    knn_track_id = track_label_to_id[knn_track_label]
    knn_k = st.sidebar.slider("k (nº de vizinhos)", 3, 30, 10, key="knn_k")
    knn_metric = st.sidebar.selectbox("Métrica", ["cosine", "euclidean"], key="knn_metric")
    knn_bpm_on = st.sidebar.checkbox("Filtrar por tolerância de BPM", value=True, key="knn_bpm_on")
    knn_bpm_tol = st.sidebar.slider("Tolerância de BPM", 1, 15, 3, key="knn_bpm_tol") if knn_bpm_on else None
    knn_camelot_on = st.sidebar.checkbox("Filtrar por key Camelot compatível", value=True, key="knn_camelot")
    knn_projection = st.sidebar.radio("Projeção de fundo", ["UMAP", "PCA"], key="knn_projection")

    st.caption(
        "Etapa 4 da fase \"3 espaços + k-NN\" (ver `docs/decisions/ADR-001-tres-espacos-e-knn.md`) — "
        "busca de faixas parecidas via `src/similarity.py`, a mesma função usada pelo assistente de "
        "LLM. BPM e key Camelot são **filtros duros** aplicados depois da busca por vizinhança, não "
        "entram na distância."
    )
    if knn_projection == "PCA":
        st.caption(
            "⚠️ PCA preserva variância global, não vizinhança local — dois pontos próximos no gráfico "
            "não são necessariamente os mais parecidos entre si. Use UMAP (padrão) pra isso; PCA aqui "
            "é só uma opção de comparação, é a mesma projeção usada na aba Clusters."
        )

    bg_df, space_features = load_space_for_knn(knn_space, restrict_ids)
    if restrict_ids is not None:
        st.caption(f"🔎 Escopo restrito: analisando {len(bg_df)} faixas classificadas (de {len(tracks_base)} na biblioteca).")

    if knn_track_id not in bg_df["track_id"].values:
        scope_hint = " dentro do escopo \"só tracks classificadas\"" if restrict_ids is not None else ""
        st.error(
            f"A faixa selecionada não está no espaço '{knn_space}'{scope_hint} — provavelmente não tem "
            "`audio_features` extraído (ver README, Limitações conhecidas)."
        )
    else:
        result = similarity_mod.similar_tracks(
            get_engine(), knn_track_id, knn_space, k=knn_k, metric=knn_metric,
            bpm_tol=knn_bpm_tol, camelot=knn_camelot_on, restrict_ids=restrict_ids,
        )
        if "error" in result:
            st.error(result["error"])
        elif not result["matches"]:
            st.warning("Nenhum vizinho passou pelos filtros de BPM/Camelot — tente afrouxar a tolerância.")
        else:
            neighbor_ids = [m["track_id"] for m in result["matches"]]
            proj_x, proj_y = ("umap_1", "umap_2") if knn_projection == "UMAP" else ("pca_1", "pca_2")

            ref_row = bg_df[bg_df.track_id == knn_track_id].iloc[0]
            neighbors_df = bg_df[bg_df.track_id.isin(neighbor_ids)]
            rest_df = bg_df[~bg_df.track_id.isin(neighbor_ids + [knn_track_id])]

            rest_label = "Resto da biblioteca" if restrict_ids is None else "Resto das faixas classificadas"

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=rest_df[proj_x], y=rest_df[proj_y], mode="markers",
                    marker=dict(color=OTHER_COLOR, size=4, opacity=0.35),
                    name=rest_label, hoverinfo="skip",
                )
            )
            sim_by_id = {m["track_id"]: m["similarity"] for m in result["matches"]}
            for nid in neighbor_ids:
                nb = bg_df[bg_df.track_id == nid]
                if nb.empty:
                    continue
                nb = nb.iloc[0]
                fig.add_trace(
                    go.Scatter(
                        x=[ref_row[proj_x], nb[proj_x]], y=[ref_row[proj_y], nb[proj_y]],
                        mode="lines", line=dict(color=CATEGORICAL_COLORS[0], width=1),
                        opacity=0.6, showlegend=False,
                        hovertemplate=f"similaridade: {sim_by_id[nid]:.3f}<extra></extra>",
                    )
                )
            fig.add_trace(
                go.Scatter(
                    x=neighbors_df[proj_x], y=neighbors_df[proj_y], mode="markers",
                    marker=dict(color=CATEGORICAL_COLORS[0], size=11, symbol="circle", line=dict(width=1, color="#fcfcfb")),
                    name="Vizinhos",
                    customdata=neighbors_df[["name", "artist", "genre", "key_camelot", "bpm"]],
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>%{customdata[1]}<br>"
                        "Gênero: %{customdata[2]}<br>Key: %{customdata[3]} · BPM: %{customdata[4]}<extra></extra>"
                    ),
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=[ref_row[proj_x]], y=[ref_row[proj_y]], mode="markers",
                    marker=dict(color=CATEGORICAL_COLORS[1], size=18, symbol="star", line=dict(width=1.5, color="#0b0b0b")),
                    name="Faixa de referência",
                    text=[ref_row["name"]],
                    hovertemplate="<b>%{text}</b> (referência)<extra></extra>",
                )
            )
            fig.update_layout(
                xaxis_title=f"{knn_projection} 1", yaxis_title=f"{knn_projection} 2",
                legend_title="Legenda",
                plot_bgcolor="#fcfcfb", paper_bgcolor="#fcfcfb",
                font=CHART_FONT,
                xaxis=dict(gridcolor="#e1e0d9", zerolinecolor="#c3c2b7"),
                yaxis=dict(gridcolor="#e1e0d9", zerolinecolor="#c3c2b7"),
                height=600,
                margin=dict(t=20),
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption(f"Referência: **{ref_row['name']}** — {ref_row['artist']}. Passe o mouse nas linhas pra ver a similaridade de cada vizinho.")

            st.subheader(f"{len(result['matches'])} vizinhos")
            table_rows = []
            for m in result["matches"]:
                def _arrow(delta):
                    if delta is None:
                        return "n/a"
                    return f"↑ {delta:.2f}" if delta > 0 else (f"↓ {delta:.2f}" if delta < 0 else f"= {delta:.2f}")

                table_rows.append(
                    {
                        "Faixa": m["name"],
                        "Artista": m["artist"],
                        "Similaridade": m["similarity"],
                        "BPM": m["bpm"],
                        "Key": m["key_camelot"],
                        "Δ brilho (centroid)": _arrow(m["delta_spectral_centroid"]),
                        "Δ energia (RMS)": _arrow(m["delta_rms_energy"]),
                    }
                )
            st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

            st.subheader("Comparar perfil: referência vs. vizinho")
            st.caption(
                "Valores padronizados (z-score: desvios-padrão em relação à média da biblioteca nesse "
                "espaço) -- eixo único e comparável entre dimensões de escalas muito diferentes (BPM em "
                "dezenas, spectral centroid em milhares)."
            )
            neighbor_labels = {f"{m['name']} — {m['artist']}": m["track_id"] for m in result["matches"]}
            chosen_label = st.selectbox("Vizinho pra comparar", list(neighbor_labels), key="knn_compare")
            chosen_id = neighbor_labels[chosen_label]

            dims = COMPARISON_DIMS[knn_space]
            dim_cols = [c for c, _ in dims]
            dim_labels = [lbl for _, lbl in dims]
            ref_values = space_features.loc[knn_track_id, dim_cols].to_numpy(dtype=float)
            neighbor_values = space_features.loc[chosen_id, dim_cols].to_numpy(dtype=float)

            # Legenda mostra o nome de verdade de cada faixa (não só "Referência"/
            # "Vizinho selecionado" genérico) -- senão não dá pra saber qual barra
            # é qual faixa sem olhar pro selectbox acima.
            ref_legend = f"Referência: {ref_row['name']}"
            neighbor_legend = f"Vizinho: {chosen_label.split(' — ')[0]}"

            fig_cmp = go.Figure()
            fig_cmp.add_trace(go.Bar(x=dim_labels, y=ref_values, name=ref_legend, marker_color=CATEGORICAL_COLORS[1]))
            fig_cmp.add_trace(go.Bar(x=dim_labels, y=neighbor_values, name=neighbor_legend, marker_color=CATEGORICAL_COLORS[0]))
            fig_cmp.update_layout(
                barmode="group",
                # font por sub-elemento (title/legend) não herda layout.font
                # automaticamente no Plotly quando parcialmente especificado --
                # sem "color" aqui, título e legenda saíam cinza-claro quase
                # invisíveis sobre o fundo claro do gráfico.
                title=dict(
                    text=f"{ref_row['name']}  vs.  {chosen_label.split(' — ')[0]}",
                    font=dict(size=13, color="#0b0b0b"),
                ),
                yaxis_title="z-score (desvios-padrão da média)",
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(color="#0b0b0b"),
                ),
                plot_bgcolor="#fcfcfb", paper_bgcolor="#fcfcfb",
                font=CHART_FONT,
                yaxis=dict(gridcolor="#e1e0d9", zerolinecolor="#c3c2b7"),
                height=380,
                margin=dict(t=90),
            )
            st.plotly_chart(fig_cmp, use_container_width=True)
