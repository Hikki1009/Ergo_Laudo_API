"""
gerar_pdf.py — Gera o laudo de Análise Ergonômica do Trabalho (AET) em PDF
a partir do objeto `laudo` exportado pelo app ErgoLaudo (React).

Uso:
    python3 gerar_pdf.py caminho/para/laudo.json caminho/para/saida.pdf

O JSON de entrada deve ter exatamente a forma do state `laudo` do AppLaudo:
{
  "dadosGerais": {...},
  "populacao": {...},
  "cargos": [...],
  "planoAcao": {...},
  "anexos": {...}
}
"""

import json
import sys
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    Image, KeepTogether, ListFlowable, ListItem, HRFlowable,
)
from reportlab.platypus.flowables import Flowable
from reportlab.pdfgen import canvas as reportlab_canvas

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import io

# ==========================================================================
# Constantes visuais — identidade ErgoLaudo (alinhada à paleta usada no app)
# ==========================================================================

COR_PRIMARIA = colors.HexColor("#0A2647")
COR_SECUNDARIA = colors.HexColor("#5B9BD5")
COR_TEXTO = colors.HexColor("#1C1F1D")
COR_TEXTO_SUAVE = colors.HexColor("#44473F")
COR_CINZA = colors.HexColor("#8A8A82")
COR_BORDA = colors.HexColor("#E5E3DC")
COR_FUNDO_SUAVE = colors.HexColor("#F7F8FA")

PALETA_GRAFICOS = ["#0A2647", "#5B9BD5", "#E0954F", "#8266B0", "#D4587A", "#7A3B4A", "#9B9A90"]

RISK_CATEGORIES = [
    {"key": "biomecanicos", "label": "Biomecânicos", "color": "#D4587A"},
    {"key": "mobiliario", "label": "Mobiliário e Equipamentos", "color": "#5B9BD5"},
    {"key": "organizacionais", "label": "Organizacionais", "color": "#8266B0"},
    {"key": "ambientais", "label": "Ambientais", "color": "#E0954F"},
    {"key": "psicossociais", "label": "Psicossociais / Cognitivos", "color": "#7A3B4A"},
]

PRIORIDADES = {
    "alta": {"label": "Alta", "color": "#C0392B", "bg": "#FBE8E6"},
    "media": {"label": "Média", "color": "#B8860B", "bg": "#FBF3DC"},
    "baixa": {"label": "Baixa", "color": "#2E7D4F", "bg": "#E8F5EC"},
}

FMEA_INDICES = [
    ("1 — Baixo", "Eventual / Esporádico", "Remota", "Boa"),
    ("2 — Médio", "Intermitente", "Improvável", "Razoável"),
    ("3 — Alto", "Habitual / Permanente", "Provável", "Ruim / Inadequada"),
]

PRIORIZACAO_RISCO = [
    ("1", "Trivial", "Ação técnica normal ou sem risco significativo.",
     "Nenhuma ação é requerida e nenhum registro documental precisa ser mantido."),
    ("2 a 3", "Tolerável", "Improvável risco à saúde do trabalhador, relaciona-se a dificuldades esporádicas.",
     "Deve-se assegurar que os meios de controle sejam mantidos e monitorados."),
    ("4 a 9", "Moderado", "Situações causadoras de fadiga se desenvolvida por longo período e/ou sem meios de controle.",
     "Devem ser implementados meios de controle/preventivos."),
    ("12 a 18", "Substancial", "Situações consideradas causadoras de lesões.",
     "Devem ser feitos estudos sistemáticos da atividade, com plano de melhoria aprovado pela alta direção."),
    ("27", "Intolerável", "Situações potencialmente causadoras de lesões, doenças e acidentes graves.",
     "Plano de melhoria de prazo imediato aprovado pela alta direção, com execução monitorada e avaliada."),
]

PERGUNTAS_ENTREVISTA = [
    ("Geral", [
        "Descreva o seu trabalho (atividades realizadas diariamente). Quando você chega, qual a primeira coisa que você faz? Qual atividade você fica na maior parte do tempo?",
        "Ferramentas que mais utiliza. Existe algum problema com as ferramentas?",
        "Relate as principais dificuldades encontradas durante a execução das suas atividades.",
    ]),
    ("Biomecânicos", [
        "Trabalha em posturas incômodas ou pouco confortáveis (ajoelhado, locais apertados, braços acima do ombro) por longos períodos? Por quanto tempo e quantas vezes?",
        "Qual a postura que fica mais na sua atividade: sentada, de pé, ou frequente deslocamento a pé? Por quanto tempo e quantas vezes (porcentagem de cada)?",
        "Seu trabalho exige esforço físico? (Não exige / Leve / Moderado / Intenso). Por quê, em qual atividade?",
        "Realiza levantamento e transporte manual de cargas ou volumes (acima de 3kg)? Qual o objeto/carga, peso aproximado, frequência, qualidade da pega, distribuição da carga?",
        "Realiza frequente ação de puxar/empurrar cargas ou volumes? Por quê, em qual atividade?",
        "Realiza frequente execução de movimentos repetitivos? Em qual atividade?",
        "Realiza frequentemente movimentos de flexão de coluna, extensão ou torção dos membros do corpo? Por quê, em qual atividade?",
        "Sofre compressão de partes do corpo com quina viva (90°) na mesa ou bancada?",
        "Usa frequentemente pedais ou alavancas? Sente dor nos membros inferiores?",
        "Realiza frequente elevação de membros superiores (braços)? Em qual atividade?",
        "Está exposto a vibrações de mão-braço ou de corpo inteiro? Sente incômodo da vibração?",
        "Usa frequentemente escadas durante o trabalho? Sente dores nos membros inferiores?",
        "Realiza trabalho intensivo com teclado ou outros dispositivos de entrada de dados? Sente dores nos membros superiores?",
    ]),
    ("Mobiliário e Equipamentos", [
        "Seu posto de trabalho é improvisado? Por quê?",
        "A cadeira é giratória, com rodízios e apoio de 5 pés, estofamento bom e regulagem de altura do encosto, assento e inclinação?",
        "Seu posto de trabalho é planejado/adaptado para a posição que fica durante sua atividade? (Medir altura, profundidade e largura da mesa ou bancada)",
        "No seu posto de trabalho os mobiliários ou equipamentos atrapalham sua movimentação do corpo, é sem espaço, apertado?",
        "No seu trabalho você precisa alcançar objetos, documentos ou controles em difícil alcance, precisando subir em suporte ou se esticar demais?",
    ]),
    ("Organizacionais", [
        "No seu trabalho são realizadas pausas pré-definidas (estabelecidas pela empresa) para descanso? Quanto tempo?",
        "Realiza pequenas pausas (micropausas espontâneas) durante sua atividade? Tem liberdade para pausar quando sente necessidade?",
        "Realiza hora extra? Com que frequência?",
        "Você considera seu ritmo de trabalho leve, moderado ou intenso? Se intenso, qual a causa?",
        "Você precisa variar de turnos ou realiza trabalho noturno? O que acha disso?",
        "Sua atividade varia bastante ou é sempre repetida (monótona)?",
        "Você é muito cobrado/pressionado para produzir cada vez mais? Por quê?",
        "Você sente que há equilíbrio entre tempo de trabalho e tempo de repouso (mínimo 11h após a jornada)?",
    ]),
    ("Ambientais", [
        "Sente desconforto em relação a algum fator ambiental: calor, ruído, umidade, iluminação ruim, piso escorregadio/irregular, reflexos em telas? Qual o motivo do desconforto?",
    ]),
    ("Psicossociais / Cognitivos", [
        "Seu trabalho gera muitas situações de estresse e sobrecarga mental? Por quê?",
        "Você é exigido a fazer múltiplas tarefas que exigem alta concentração, atenção e memória? Por quê?",
        "Como é a comunicação no seu trabalho, entre colegas e líder? (Ótima / Boa / Razoável / Ruim)",
        "Há muitos conflitos no trabalho (entre colegas, setores, hierarquia, demandas divergentes)? Qual tipo?",
        "Você se encontra satisfeito com seu trabalho? Por quê?",
        "Você possui autonomia no seu trabalho? Te dão liberdade para resolver ou dar sua opinião?",
        "O que você considera pontos positivos da empresa?",
        "Você possui sugestões de melhoria em relação à sua atividade ou algo que observou na empresa?",
        "Você sente algum tipo de dor no corpo? Qual local? Acha que está relacionada à atividade que executa?",
        "Você já foi afastado do trabalho por doença ocupacional ou acidente de trabalho? Qual motivo?",
    ]),
]


def get_styles():
    """Monta a folha de estilos usada em todo o documento."""
    base = getSampleStyleSheet()
    styles = {}

    styles["CapaTitulo"] = ParagraphStyle(
        "CapaTitulo", parent=base["Title"], fontName="Helvetica-Bold",
        fontSize=22, leading=27, textColor=COR_PRIMARIA, alignment=TA_CENTER,
        spaceAfter=6,
    )
    styles["CapaSubtitulo"] = ParagraphStyle(
        "CapaSubtitulo", parent=base["Normal"], fontName="Helvetica",
        fontSize=12, leading=16, textColor=COR_TEXTO_SUAVE, alignment=TA_CENTER,
    )
    styles["CapaInfo"] = ParagraphStyle(
        "CapaInfo", parent=base["Normal"], fontName="Helvetica",
        fontSize=10.5, leading=15, textColor=COR_TEXTO, alignment=TA_CENTER,
    )

    styles["TituloSecao"] = ParagraphStyle(
        "TituloSecao", parent=base["Heading1"], fontName="Helvetica-Bold",
        fontSize=15, leading=19, textColor=COR_PRIMARIA, spaceBefore=4, spaceAfter=10,
    )
    styles["TituloSubsecao"] = ParagraphStyle(
        "TituloSubsecao", parent=base["Heading2"], fontName="Helvetica-Bold",
        fontSize=12, leading=16, textColor=COR_PRIMARIA, spaceBefore=10, spaceAfter=6,
    )
    styles["TituloCargo"] = ParagraphStyle(
        "TituloCargo", parent=base["Heading1"], fontName="Helvetica-Bold",
        fontSize=16, leading=20, textColor=colors.white, spaceBefore=0, spaceAfter=0,
    )

    styles["Corpo"] = ParagraphStyle(
        "Corpo", parent=base["Normal"], fontName="Helvetica", fontSize=10,
        leading=14.5, textColor=COR_TEXTO, alignment=TA_JUSTIFY, spaceAfter=8,
    )
    styles["CorpoEsq"] = ParagraphStyle(
        "CorpoEsq", parent=base["Normal"], fontName="Helvetica", fontSize=10,
        leading=14.5, textColor=COR_TEXTO, alignment=TA_LEFT, spaceAfter=6,
    )
    styles["Rotulo"] = ParagraphStyle(
        "Rotulo", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9,
        leading=12, textColor=COR_TEXTO_SUAVE, spaceAfter=2,
    )
    styles["Valor"] = ParagraphStyle(
        "Valor", parent=base["Normal"], fontName="Helvetica", fontSize=10,
        leading=13.5, textColor=COR_TEXTO, spaceAfter=8,
    )
    styles["Rodape"] = ParagraphStyle(
        "Rodape", parent=base["Normal"], fontName="Helvetica", fontSize=8,
        leading=10, textColor=COR_CINZA, alignment=TA_CENTER,
    )
    styles["NotaPequena"] = ParagraphStyle(
        "NotaPequena", parent=base["Normal"], fontName="Helvetica-Oblique", fontSize=8.5,
        leading=11.5, textColor=COR_CINZA, spaceAfter=8,
    )
    styles["PerguntaCategoria"] = ParagraphStyle(
        "PerguntaCategoria", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=10,
        leading=13, textColor=COR_PRIMARIA, spaceBefore=10, spaceAfter=4,
    )
    styles["PerguntaItem"] = ParagraphStyle(
        "PerguntaItem", parent=base["Normal"], fontName="Helvetica", fontSize=9,
        leading=12.5, textColor=COR_TEXTO, spaceAfter=5,
    )
    return styles


def safe(value, fallback="—"):
    """Retorna o valor como string, ou um placeholder se vazio."""
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def hr(color=COR_BORDA, thickness=0.75, space_before=2, space_after=10):
    return HRFlowable(width="100%", thickness=thickness, color=color,
                       spaceBefore=space_before, spaceAfter=space_after)


# ==========================================================================
# Gráficos (matplotlib, renderizados como imagem e inseridos no PDF)
# ==========================================================================

def _fig_to_image(fig, width=8.5 * cm):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight", transparent=False)
    plt.close(fig)
    buf.seek(0)
    img = Image(buf)
    aspect = img.imageHeight / float(img.imageWidth)
    img.drawWidth = width
    img.drawHeight = width * aspect
    return img


def grafico_pizza(data, titulo, width=8 * cm):
    """data: lista de {label, valor}. Pula se não houver nenhum valor > 0."""
    labels, valores = [], []
    for item in data:
        v = float(item.get("valor") or 0)
        if v > 0:
            labels.append(item["label"])
            valores.append(v)
    if not valores:
        return None
    fig, ax = plt.subplots(figsize=(4.2, 3.4))
    cores = [PALETA_GRAFICOS[i % len(PALETA_GRAFICOS)] for i in range(len(valores))]
    ax.pie(valores, labels=None, autopct="%1.0f%%", colors=cores,
           textprops={"fontsize": 8, "color": "white", "fontweight": "bold"},
           wedgeprops={"linewidth": 0.5, "edgecolor": "white"})
    ax.legend(labels, loc="center left", bbox_to_anchor=(1.0, 0.5),
               fontsize=7.5, frameon=False)
    ax.set_title(titulo, fontsize=9.5, color="#1C1F1D", fontweight="bold", pad=8)
    fig.tight_layout()
    return _fig_to_image(fig, width=width)


def grafico_barra(data, titulo, horizontal=True, width=10 * cm):
    labels, valores = [], []
    for item in data:
        v = float(item.get("valor") or 0)
        labels.append(item["label"])
        valores.append(v)
    if not any(v > 0 for v in valores):
        return None
    cores = [PALETA_GRAFICOS[i % len(PALETA_GRAFICOS)] for i in range(len(valores))]
    fig_h = max(2.2, 0.45 * len(labels)) if horizontal else 3.2
    fig, ax = plt.subplots(figsize=(5.6, fig_h))
    if horizontal:
        y_pos = range(len(labels))
        ax.barh(y_pos, valores, color=cores)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=8)
        ax.invert_yaxis()
        for i, v in enumerate(valores):
            ax.text(v + max(valores) * 0.02, i, str(int(v)), va="center", fontsize=8)
    else:
        x_pos = range(len(labels))
        ax.bar(x_pos, valores, color=cores)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(labels, fontsize=7.5, rotation=20, ha="right")
        for i, v in enumerate(valores):
            ax.text(i, v + max(valores) * 0.02, str(int(v)), ha="center", fontsize=8)
    ax.set_title(titulo, fontsize=9.5, color="#1C1F1D", fontweight="bold", pad=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return _fig_to_image(fig, width=width)


def grafico_sim_nao(sim, nao, titulo, sim_label="Sim", nao_label="Não", width=7 * cm):
    sim_v, nao_v = float(sim or 0), float(nao or 0)
    if sim_v <= 0 and nao_v <= 0:
        return None
    fig, ax = plt.subplots(figsize=(3.6, 3.0))
    ax.pie([sim_v, nao_v], labels=[sim_label, nao_label], autopct="%1.0f%%",
           colors=["#0A2647", "#D8D6CD"],
           textprops={"fontsize": 8.5, "fontweight": "bold"},
           wedgeprops={"linewidth": 0.5, "edgecolor": "white"})
    ax.set_title(titulo, fontsize=9, color="#1C1F1D", fontweight="bold", pad=6)
    fig.tight_layout()
    return _fig_to_image(fig, width=width)


# ==========================================================================
# Capítulo: Capa
# ==========================================================================

def montar_capa(laudo, styles):
    flow = []
    empresa = laudo["dadosGerais"]["empresa"]
    responsavel = laudo["dadosGerais"]["responsavel"]

    flow.append(Spacer(1, 3 * cm))
    flow.append(Paragraph("ANÁLISE ERGONÔMICA DO TRABALHO", styles["CapaTitulo"]))
    flow.append(Spacer(1, 0.3 * cm))
    flow.append(Paragraph(safe(empresa.get("razaoSocial"), "Empresa não informada"), styles["CapaSubtitulo"]))
    flow.append(Spacer(1, 4 * cm))

    flow.append(Paragraph("<b>Responsável Técnico:</b>", styles["CapaInfo"]))
    flow.append(Paragraph(
        f"{safe(responsavel.get('nome'))}<br/>"
        f"{safe(responsavel.get('formacao'))} — CREFITO {safe(responsavel.get('crefito'))}",
        styles["CapaInfo"]
    ))
    flow.append(Spacer(1, 1.2 * cm))

    flow.append(Paragraph(f"<b>Empresa:</b> {safe(empresa.get('razaoSocial'))}", styles["CapaInfo"]))
    flow.append(Paragraph(f"<b>Local:</b> {safe(empresa.get('enderecoLocal'))}", styles["CapaInfo"]))
    flow.append(Spacer(1, 2.5 * cm))

    MESES_PT = [
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    ]
    agora = datetime.now()
    data_hoje = f"{agora.day:02d} de {MESES_PT[agora.month - 1]} de {agora.year}"
    flow.append(Paragraph(safe(empresa.get("enderecoLocal"), "") + f", {data_hoje}.", styles["CapaInfo"]))
    flow.append(PageBreak())
    return flow


# ==========================================================================
# Capítulo: Identificação (Empresa / Contrato / Responsável)
# ==========================================================================

def _tabela_chave_valor(pares, styles, col_widths=(5 * cm, 11.5 * cm)):
    """pares: lista de (rótulo, valor)."""
    rows = []
    for rotulo, valor in pares:
        rows.append([
            Paragraph(rotulo, styles["Rotulo"]),
            Paragraph(safe(valor), styles["Valor"]),
        ])
    t = Table(rows, colWidths=list(col_widths))
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, COR_BORDA),
    ]))
    return t


def montar_identificacao(laudo, styles):
    flow = []
    dg = laudo["dadosGerais"]
    empresa, contrato, responsavel = dg["empresa"], dg["contrato"], dg["responsavel"]

    flow.append(Paragraph("IDENTIFICAÇÃO DA EMPRESA", styles["TituloSecao"]))
    flow.append(_tabela_chave_valor([
        ("Razão Social", empresa.get("razaoSocial")),
        ("CNPJ", empresa.get("cnpj")),
        ("CNAE", empresa.get("cnae")),
        ("Grau de Risco", empresa.get("grauRisco")),
        ("Endereço do Local Avaliado", empresa.get("enderecoLocal")),
        ("Endereço dos Serviços", empresa.get("enderecoServicos")),
        ("Atividade Principal", empresa.get("atividadePrincipal")),
    ], styles))
    flow.append(Spacer(1, 14))

    flow.append(Paragraph("IDENTIFICAÇÃO DO CONTRATO", styles["TituloSecao"]))
    flow.append(_tabela_chave_valor([
        ("Identificação do Contrato", contrato.get("identificacao")),
        ("Objetivo", contrato.get("objetivo")),
        ("Contratante", contrato.get("contratante")),
        ("Vigência", contrato.get("vigencia")),
        ("Gestor do Contrato", contrato.get("gestor")),
        ("Fiscal do Contrato", contrato.get("fiscal")),
        ("Grau de Risco — Contratante", contrato.get("grauRiscoContratante")),
        ("Grau de Risco — Contratada", contrato.get("grauRiscoContratada")),
    ], styles))
    flow.append(Spacer(1, 14))

    flow.append(Paragraph("RESPONSÁVEL TÉCNICO PELA ELABORAÇÃO DA AET", styles["TituloSecao"]))
    flow.append(_tabela_chave_valor([
        ("Nome", responsavel.get("nome")),
        ("CREFITO", responsavel.get("crefito")),
        ("Formação", responsavel.get("formacao")),
        ("Empresa de Consultoria", responsavel.get("empresaConsultoria")),
        ("CNPJ da Consultoria", responsavel.get("cnpjConsultoria")),
        ("Endereço", responsavel.get("endereco")),
        ("Contato", responsavel.get("contato")),
    ], styles))
    flow.append(PageBreak())
    return flow


# ==========================================================================
# Capítulo: Corpo teórico (Introdução, Conceito, Legislação, Demanda, Metodologia)
# ==========================================================================

def _texto_em_paragrafos(texto, style):
    """Quebra um texto multi-linha (parágrafos separados por linha vazia) em Paragraphs."""
    flow = []
    for bloco in safe(texto, "").split("\n\n"):
        bloco = bloco.strip()
        if bloco:
            bloco_html = bloco.replace("\n", "<br/>")
            flow.append(Paragraph(bloco_html, style))
    return flow


def montar_corpo_teorico(laudo, styles):
    flow = []
    textos = laudo["dadosGerais"]["textos"]

    flow.append(Paragraph("1. INTRODUÇÃO", styles["TituloSecao"]))
    flow += _texto_em_paragrafos(textos.get("introducao"), styles["Corpo"])

    flow.append(Paragraph("1.1 Conceito de Ergonomia", styles["TituloSubsecao"]))
    flow += _texto_em_paragrafos(textos.get("conceito"), styles["Corpo"])

    flow.append(Paragraph("1.2 Legislação", styles["TituloSubsecao"]))
    flow += _texto_em_paragrafos(textos.get("legislacao"), styles["Corpo"])
    flow.append(PageBreak())

    flow.append(Paragraph("2. ANÁLISE E CONSTITUIÇÃO DA DEMANDA", styles["TituloSecao"]))
    flow += _texto_em_paragrafos(textos.get("demanda"), styles["Corpo"])

    flow.append(Paragraph("3. MÉTODOS E METODOLOGIA", styles["TituloSecao"]))
    flow += _texto_em_paragrafos(textos.get("metodologia"), styles["Corpo"])
    flow.append(PageBreak())
    return flow


# ==========================================================================
# Capítulo: População
# ==========================================================================

def montar_populacao(laudo, styles):
    flow = []
    pop = laudo["populacao"]

    flow.append(Paragraph("4. EXPLORAÇÃO DO FUNCIONAMENTO DA EMPRESA", styles["TituloSecao"]))
    flow.append(Paragraph("4.1 Caracterização da População Estudada", styles["TituloSubsecao"]))

    total_m = int(pop.get("totalMasculino") or 0)
    total_f = int(pop.get("totalFeminino") or 0)
    resumo = _tabela_chave_valor([
        ("Total de Homens", f"{total_m} (idade média: {safe(pop.get('idadeMediaMasculino'))} anos)"),
        ("Total de Mulheres", f"{total_f} (idade média: {safe(pop.get('idadeMediaFeminino'))} anos)"),
        ("Total Geral", str(total_m + total_f)),
    ], styles)
    flow.append(resumo)
    flow.append(Spacer(1, 12))

    # Gráficos lado a lado / em sequência conforme espaço
    img_escolaridade = grafico_pizza(pop["escolaridade"], "Escolaridade")
    img_tempo = grafico_pizza(pop["tempoEmpresa"], "Tempo na Empresa")
    img_queixas = grafico_barra(pop["queixas"], "Queixas Musculoesqueléticas", horizontal=True)
    img_posturas = grafico_barra(pop["posturas"], "Posturas Adotadas", horizontal=True)

    img_transporte = grafico_sim_nao(pop["transporteCargas"]["sim"], pop["transporteCargas"]["nao"],
                                      "Transporte de Cargas")
    img_micropausas = grafico_sim_nao(pop["micropausas"]["sim"], pop["micropausas"]["nao"],
                                       "Micropausas")
    img_autonomia = grafico_sim_nao(pop["autonomia"]["sim"], pop["autonomia"]["nao"],
                                     "Autonomia")
    img_comunicacao = grafico_sim_nao(pop["comunicacao"]["eficaz"], pop["comunicacao"]["falhas"],
                                       "Comunicação", sim_label="Eficaz", nao_label="Com falhas")

    def linha_dupla(img_a, img_b):
        if img_a is None and img_b is None:
            return None
        cell_a = img_a if img_a else Paragraph("Sem dados suficientes para o gráfico.", styles["NotaPequena"])
        cell_b = img_b if img_b else Paragraph("Sem dados suficientes para o gráfico.", styles["NotaPequena"])
        t = Table([[cell_a, cell_b]], colWidths=[8.3 * cm, 8.3 * cm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    for par in [(img_escolaridade, img_tempo), (img_queixas, img_posturas),
                (img_transporte, img_micropausas), (img_autonomia, img_comunicacao)]:
        linha = linha_dupla(*par)
        if linha:
            flow.append(linha)
            flow.append(Spacer(1, 10))

    flow.append(PageBreak())
    return flow


# ==========================================================================
# Capítulo: Cargos (bloco repetível)
# ==========================================================================

def _tabela_rula(rula, styles):
    headers = ["Segmento", "Direito", "Esquerdo"]
    rows = [
        ["Ombro", safe(rula.get("ombroD"), "-"), safe(rula.get("ombroE"), "-")],
        ["Antebraço", safe(rula.get("antebracoD"), "-"), safe(rula.get("antebracoE"), "-")],
        ["Punho", safe(rula.get("punhoD"), "-"), safe(rula.get("punhoE"), "-")],
        ["Pescoço", safe(rula.get("pescoco"), "-"), ""],
        ["Tronco", safe(rula.get("tronco"), "-"), ""],
        ["Pernas", safe(rula.get("pernas"), "-"), ""],
        ["Resultado Final", safe(rula.get("finalD"), "-"), safe(rula.get("finalE"), "-")],
    ]
    data = [headers] + rows
    t = Table(data, colWidths=[6 * cm, 4 * cm, 4 * cm])
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), COR_PRIMARIA),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, COR_BORDA),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, COR_FUNDO_SUAVE]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FCEEF1")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    t.setStyle(TableStyle(style))
    return t


def _tabela_riscos_cargo(riscos, styles):
    rows = []
    for cat in RISK_CATEGORIES:
        texto = safe(riscos.get(cat["key"]), "Não foram identificados fatores de risco relevantes nesta categoria.")
        rows.append([
            Paragraph(f'<font color="{cat["color"]}"><b>{cat["label"]}</b></font>', styles["Rotulo"]),
            Paragraph(texto, styles["Valor"]),
        ])
    t = Table(rows, colWidths=[4.5 * cm, 12 * cm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, COR_BORDA),
    ]))
    return t


def montar_cargos(laudo, styles):
    flow = []
    cargos = laudo.get("cargos", [])

    flow.append(Paragraph("5. ANÁLISE ERGONÔMICA POR CARGO", styles["TituloSecao"]))
    if not cargos:
        flow.append(Paragraph(
            "Nenhum cargo foi cadastrado neste laudo até o momento da geração deste PDF.",
            styles["Corpo"]
        ))
        flow.append(PageBreak())
        return flow

    for idx, cargo in enumerate(cargos, start=1):
        bloco = []
        cond = cargo.get("condicoes", {})

        # Cabeçalho do cargo (faixa colorida)
        nome_tbl = Table(
            [[Paragraph(f"5.{idx} {safe(cargo.get('nome'), 'Cargo sem nome')}", styles["TituloCargo"])]],
            colWidths=[16.5 * cm]
        )
        nome_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COR_PRIMARIA),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        bloco.append(nome_tbl)
        bloco.append(Spacer(1, 10))

        bloco.append(Paragraph("Condições de Trabalho", styles["TituloSubsecao"]))
        bloco.append(_tabela_chave_valor([
            ("Instalações", cond.get("instalacoes")),
            ("Descrição da Função", cond.get("descricaoFuncao")),
            ("Ferramentas Utilizadas", cond.get("ferramentas")),
            ("Jornada", cond.get("jornada")),
            ("Pausas", cond.get("pausas")),
            ("Ritmo de Trabalho", cond.get("ritmo")),
            ("Postura Predominante", cond.get("postura")),
            ("Aspectos Cognitivos", cond.get("aspectosCognitivos")),
            ("Mobiliário", cond.get("mobiliario")),
            ("Atividades Rotineiras", cond.get("atividadesRotineiras")),
        ], styles, col_widths=(4.5 * cm, 12 * cm)))
        bloco.append(Spacer(1, 10))

        # Registro fotográfico
        fotos = cargo.get("fotos", [])
        if fotos:
            bloco.append(Paragraph("Registro Fotográfico", styles["TituloSubsecao"]))
            for foto in fotos:
                src = foto.get("src", "")
                if src.startswith("data:image"):
                    try:
                        header, b64data = src.split(",", 1)
                        import base64
                        img_bytes = base64.b64decode(b64data)
                        img_buf = io.BytesIO(img_bytes)
                        img = Image(img_buf)
                        max_w = 10 * cm
                        aspect = img.imageHeight / float(img.imageWidth)
                        img.drawWidth = max_w
                        img.drawHeight = max_w * aspect
                        bloco.append(img)
                        if foto.get("legenda"):
                            bloco.append(Paragraph(foto["legenda"], styles["NotaPequena"]))
                        bloco.append(Spacer(1, 6))
                    except Exception:
                        bloco.append(Paragraph("[Não foi possível incluir uma das fotos deste cargo]",
                                                styles["NotaPequena"]))
            bloco.append(Spacer(1, 6))

        bloco.append(KeepTogether([
            Paragraph("Riscos Ergonômicos Identificados (categorias eSocial)", styles["TituloSubsecao"]),
            _tabela_riscos_cargo(cargo.get("riscos", {}), styles),
        ]))
        bloco.append(Spacer(1, 10))

        bloco.append(KeepTogether([
            Paragraph("Avaliação RULA (Rapid Upper Limb Assessment)", styles["TituloSubsecao"]),
            _tabela_rula(cargo.get("rula", {}), styles),
        ]))
        bloco.append(Spacer(1, 10))

        bloco.append(Paragraph("Conclusão e Recomendações", styles["TituloSubsecao"]))
        bloco.append(Paragraph(safe(cargo.get("conclusao"), "Sem conclusão registrada para este cargo."),
                                styles["Corpo"]))
        recs = [r for r in cargo.get("recomendacoes", []) if r and r.strip()]
        if recs:
            itens = [ListItem(Paragraph(r, styles["CorpoEsq"]), leftIndent=12) for r in recs]
            bloco.append(ListFlowable(itens, bulletType="bullet", start="•"))

        flow.append(KeepTogether(bloco[:3]))
        flow.extend(bloco[3:])
        flow.append(PageBreak())

    return flow


# ==========================================================================
# Capítulo: Plano de Ação
# ==========================================================================

def montar_plano_acao(laudo, styles):
    flow = []
    plano = laudo.get("planoAcao", {})
    acoes = plano.get("acoes", [])

    flow.append(Paragraph("6. RESULTADOS E DISCUSSÃO", styles["TituloSecao"]))
    flow.append(Paragraph(
        "A partir da análise dos dados coletados em campo, foram identificados os riscos ergonômicos "
        "descritos individualmente em cada cargo avaliado neste laudo, com base na ferramenta FMEA e "
        "na avaliação postural RULA. As recomendações decorrentes dessa análise estão detalhadas no "
        "Plano de Ação a seguir.", styles["Corpo"]
    ))
    flow.append(Spacer(1, 8))

    flow.append(Paragraph("7. PLANO DE AÇÃO", styles["TituloSecao"]))

    if not acoes:
        flow.append(Paragraph("Nenhuma ação foi cadastrada neste laudo até o momento da geração deste PDF.",
                               styles["Corpo"]))
    else:
        contagem = {"alta": 0, "media": 0, "baixa": 0}
        for acao in acoes:
            contagem[acao.get("prioridade", "media")] = contagem.get(acao.get("prioridade", "media"), 0) + 1

        resumo_tbl = Table(
            [["Prioridade", "Quantidade"]] + [
                [PRIORIDADES[k]["label"], str(contagem.get(k, 0))] for k in ["alta", "media", "baixa"]
            ],
            colWidths=[8 * cm, 8 * cm]
        )
        resumo_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COR_PRIMARIA),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("GRID", (0, 0), (-1, -1), 0.5, COR_BORDA),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#FBE8E6")),
            ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#FBF3DC")),
            ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#E8F5EC")),
        ]))
        flow.append(resumo_tbl)
        flow.append(Spacer(1, 14))

        headers = ["PR", "O quê", "Por quê", "Quem", "Como", "Onde", "Quando"]
        rows = [headers]
        row_colors = []
        for acao in acoes:
            prio = PRIORIDADES.get(acao.get("prioridade", "media"), PRIORIDADES["media"])
            rows.append([
                Paragraph(f'<font color="{prio["color"]}"><b>{prio["label"]}</b></font>', styles["Valor"]),
                Paragraph(safe(acao.get("oQue")), styles["Valor"]),
                Paragraph(safe(acao.get("porQue")), styles["Valor"]),
                Paragraph(safe(acao.get("quem")), styles["Valor"]),
                Paragraph(safe(acao.get("como")), styles["Valor"]),
                Paragraph(safe(acao.get("onde")), styles["Valor"]),
                Paragraph(safe(acao.get("quando")), styles["Valor"]),
            ])
            row_colors.append(colors.HexColor(prio["bg"]))

        t = Table(rows, colWidths=[1.6 * cm, 2.6 * cm, 2.6 * cm, 2.0 * cm, 2.6 * cm, 2.6 * cm, 2.1 * cm])
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), COR_PRIMARIA),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, COR_BORDA),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
        for i, bg in enumerate(row_colors, start=1):
            style.append(("BACKGROUND", (0, i), (0, i), bg))
        t.setStyle(TableStyle(style))
        flow.append(t)

    flow.append(Spacer(1, 14))
    flow.append(Paragraph("8. CONSIDERAÇÕES FINAIS", styles["TituloSecao"]))
    flow += _texto_em_paragrafos(plano.get("consideracoes"), styles["Corpo"])
    flow.append(PageBreak())
    return flow


# ==========================================================================
# Capítulo: Anexos
# ==========================================================================

def montar_anexos(laudo, styles):
    flow = []
    anexos = laudo.get("anexos", {})

    flow.append(Paragraph("APÊNDICE 1 — ROTEIRO DE ENTREVISTA", styles["TituloSecao"]))
    for categoria, perguntas in PERGUNTAS_ENTREVISTA:
        flow.append(Paragraph(categoria, styles["PerguntaCategoria"]))
        itens = [ListItem(Paragraph(p, styles["PerguntaItem"]), leftIndent=10) for p in perguntas]
        flow.append(ListFlowable(itens, bulletType="bullet", start="•"))
    flow.append(PageBreak())

    flow.append(Paragraph("ANEXO 1 — ÍNDICES DE DETERMINAÇÃO DO FMEA", styles["TituloSecao"]))
    rows = [["Índice", "Ocorrência", "Severidade", "Condição Ergonômica"]] + list(FMEA_INDICES)
    t = Table(rows, colWidths=[3 * cm, 4.5 * cm, 4.5 * cm, 4.5 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COR_PRIMARIA),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, COR_BORDA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COR_FUNDO_SUAVE]),
    ]))
    flow.append(t)
    flow.append(Spacer(1, 18))

    flow.append(Paragraph("ANEXO 2 — NÍVEIS DE PRIORIZAÇÃO DE RISCO", styles["TituloSecao"]))
    rows = [["Nível", "Caracterização", "Descrição", "Equivalência OHSAS 18001/BS 8800"]]
    for nivel, carac, desc, ohsas in PRIORIZACAO_RISCO:
        rows.append([
            Paragraph(f"<b>{nivel}</b>", styles["Valor"]),
            Paragraph(carac, styles["Valor"]),
            Paragraph(desc, styles["Valor"]),
            Paragraph(ohsas, styles["Valor"]),
        ])
    t = Table(rows, colWidths=[1.8 * cm, 2.7 * cm, 5.5 * cm, 6.5 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COR_PRIMARIA),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, COR_BORDA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COR_FUNDO_SUAVE]),
    ]))
    flow.append(t)
    flow.append(PageBreak())

    flow.append(Paragraph("ANEXO 3 — TABELA RULA", styles["TituloSecao"]))
    flow.append(Paragraph(
        "Tabela de referência do método RULA (Rapid Upper Limb Assessment), utilizada para a "
        "pontuação postural de cada cargo avaliado neste laudo. As pontuações por segmento corporal "
        "constam na seção de cada cargo, no capítulo 5 deste documento.", styles["Corpo"]
    ))
    flow.append(Spacer(1, 16))

    flow.append(Paragraph("ANEXO 4 — CERTIFICADO DE CAPACITAÇÃO", styles["TituloSecao"]))
    cert = anexos.get("certificado")
    if cert and isinstance(cert, str) and cert.startswith("data:"):
        try:
            header, b64data = cert.split(",", 1)
            import base64
            if "image" in header:
                img_bytes = base64.b64decode(b64data)
                img_buf = io.BytesIO(img_bytes)
                img = Image(img_buf)
                max_w = 14 * cm
                aspect = img.imageHeight / float(img.imageWidth)
                img.drawWidth = max_w
                img.drawHeight = max_w * aspect
                flow.append(img)
            else:
                flow.append(Paragraph(
                    "Certificado anexado em formato PDF — não exibido inline; "
                    "arquivo original deve acompanhar a entrega deste laudo.",
                    styles["Corpo"]
                ))
        except Exception:
            flow.append(Paragraph("[Não foi possível incluir o certificado anexado]", styles["NotaPequena"]))
    else:
        flow.append(Paragraph(
            "Nenhum certificado de capacitação foi anexado a este laudo até o momento da geração deste PDF.",
            styles["Corpo"]
        ))

    return flow


# ==========================================================================
# Cabeçalho/rodapé de página
# ==========================================================================

def _cabecalho_rodape(canvas_obj: reportlab_canvas.Canvas, doc, laudo):
    canvas_obj.saveState()
    width, height = A4
    empresa_nome = safe(laudo["dadosGerais"]["empresa"].get("razaoSocial"), "")

    # Rodapé
    canvas_obj.setStrokeColor(COR_BORDA)
    canvas_obj.setLineWidth(0.5)
    canvas_obj.line(2 * cm, 1.5 * cm, width - 2 * cm, 1.5 * cm)
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.setFillColor(COR_CINZA)
    canvas_obj.drawString(2 * cm, 1.1 * cm, empresa_nome[:70])
    canvas_obj.drawRightString(width - 2 * cm, 1.1 * cm, f"Página {doc.page}")
    canvas_obj.restoreState()


def gerar_pdf(laudo, caminho_saida):
    """Gera o PDF do laudo a partir do dicionário `laudo` (mesma forma do state React)."""
    styles = get_styles()

    doc = SimpleDocTemplate(
        caminho_saida, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2.2 * cm,
        title="Análise Ergonômica do Trabalho",
    )

    story = []
    story += montar_capa(laudo, styles)
    story += montar_identificacao(laudo, styles)
    story += montar_corpo_teorico(laudo, styles)
    story += montar_populacao(laudo, styles)
    story += montar_cargos(laudo, styles)
    story += montar_plano_acao(laudo, styles)
    story += montar_anexos(laudo, styles)

    def on_page(canvas_obj, doc_obj):
        _cabecalho_rodape(canvas_obj, doc_obj, laudo)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)


def main():
    if len(sys.argv) < 3:
        print("Uso: python3 gerar_pdf.py entrada.json saida.pdf")
        sys.exit(1)

    caminho_json = sys.argv[1]
    caminho_pdf = sys.argv[2]

    with open(caminho_json, "r", encoding="utf-8") as f:
        laudo = json.load(f)

    gerar_pdf(laudo, caminho_pdf)
    print(f"PDF gerado com sucesso: {caminho_pdf}")


if __name__ == "__main__":
    main()
