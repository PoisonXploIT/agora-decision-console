"""report.py - informe PDF de decisiones, en lenguaje de ejecutivo y con graficos.

Genera un PDF a partir de un conjunto de decisiones ya calculadas:

    results = [
      {
        "question_id": "...", "prompt": "...", "type": "choice",
        "by_backend": [
          {"backend": "laya", "model": "laya-rl-agent", "latency_ms": 63.0,
           "probabilities": {"a": 0.45, "b": 0.21, "c": 0.34},
           "expected": None, "action": None},
          ...
        ],
      },
      ...
    ]

Solo depende de reportlab (dibuja texto y graficos vectoriales).
"""
from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

AZUL = colors.HexColor("#1f6feb")
CIAN = colors.HexColor("#38bdf8")
VERDE = colors.HexColor("#2ea043")
GRIS = colors.HexColor("#6b7280")
GRIS_CLARO = colors.HexColor("#eef2f6")
ROJO = colors.HexColor("#d1242f")
AMBAR = colors.HexColor("#d29922")


def _banda(conf: float) -> tuple[str, colors.Color]:
    """Lectura rapida de una probabilidad maxima, para ejecutivos."""
    if conf >= 0.75:
        return "alta", VERDE
    if conf >= 0.55:
        return "media", AMBAR
    return "baja", ROJO


def _drawwidth() -> float:
    return A4[0] - 40 * mm


def _bar_chart(labels: list[str], values: list[float], *, height: float = 30 * mm) -> Drawing:
    """Barra horizontal con el ganador resaltado."""
    ancho = _drawwidth()
    n = max(1, len(labels))
    d = Drawing(ancho, max(height, 12 * mm * n))
    chart = HorizontalBarChart()
    chart.x = 90
    chart.y = 8
    chart.width = ancho - 110
    chart.height = d.height - 16
    chart.data = [values]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontSize = 8
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 1
    chart.valueAxis.valueStep = 0.25
    chart.valueAxis.labels.fontSize = 7
    chart.bars[0].strokeColor = None
    top = max(range(len(values)), key=lambda i: values[i]) if values else 0
    chart.bars[0].fillColor = VERDE
    # resaltar el ganador: una sola barra de color fuerte, el resto en azul claro
    try:
        chart.bars[(0, top)].fillColor = VERDE
        for i in range(len(values)):
            if i != top:
                chart.bars[(0, i)].fillColor = CIAN
    except Exception:
        chart.bars[0].fillColor = CIAN
    d.add(chart)
    return d


def _verdict_line(prompt: str, probs: dict[str, float], qtype: str,
                  expected: float | None, action: str | None) -> str:
    if not probs:
        return "sin resultado"
    top = max(probs, key=probs.get)
    conf = probs[top]
    banda, _ = _banda(conf)
    if qtype == "score" and expected is not None:
        return f"Resultado: nivel <b>{expected:.2f}</b> (moda {top!r}); confianza {banda}"
    extra = f"; accion <b>{action}</b>" if action else ""
    return f"Resultado: <b>{top}</b> con probabilidad <b>{conf:.2f}</b>; confianza {banda}{extra}"


def build_pdf(*, title: str, generated_at: str, results: list[dict[str, Any]],
              backends: list[str], state_label: str = "") -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=16 * mm,
        title=title, author="AGORA",
    )
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=22, leading=26, textColor=AZUL, alignment=TA_LEFT)
    sub = ParagraphStyle("sub", parent=ss["Normal"], fontSize=10, textColor=GRIS)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=13, textColor=colors.HexColor("#111827"), spaceBefore=6)
    body = ParagraphStyle("body", parent=ss["Normal"], fontSize=10, leading=14)
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=8.5, textColor=GRIS)

    story: list[Any] = []
    story.append(Paragraph(title, h1))
    story.append(Paragraph(f"Informe ejecutivo de decisiones tipadas. Generado {generated_at}.", sub))
    story.append(Spacer(1, 6 * mm))

    # ---- resumen ----
    n_dec = sum(len(r.get("by_backend") or []) for r in results)
    acuerdos = []
    for r in results:
        tops = [max(b["probabilities"], key=b["probabilities"].get)
                for b in (r.get("by_backend") or []) if b.get("probabilities")]
        if len(tops) > 1:
            acuerdos.append(len(set(tops)) == 1)
    acuerdo_txt = "-"
    if acuerdos:
        acuerdo_txt = f"{100 * sum(acuerdos) / len(acuerdos):.0f}%"
    resumen = [
        ["Preguntas evaluadas", str(len(results))],
        ["Decisiones calculadas", str(n_dec)],
        ["Modelos de decision", ", ".join(backends) or "-"],
        ["Acuerdo entre modelos", acuerdo_txt],
    ]
    if state_label:
        resumen.insert(0, ["Estado evaluado", state_label])
    t = Table(resumen, colWidths=[55 * mm, _drawwidth() - 55 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), GRIS_CLARO),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#111827")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#dbe1e8")),
    ]))
    story.append(t)
    story.append(Spacer(1, 8 * mm))

    # ---- por pregunta ----
    for r in results:
        by = r.get("by_backend") or []
        bloque: list[Any] = [
            Paragraph(f"{r.get('question_id', '')} · {r.get('prompt', '')}", h2),
            Paragraph(f"Tipo: <b>{r.get('type', '')}</b>", small),
            Spacer(1, 3 * mm),
        ]
        primero = by[0] if by else {}
        probs = primero.get("probabilities") or {}
        if probs:
            bloque.append(Paragraph(
                _verdict_line(r.get("prompt", ""), probs, r.get("type", ""),
                              primero.get("expected"), primero.get("action")),
                body,
            ))
            bloque.append(Spacer(1, 2 * mm))
            orden = sorted(probs.items(), key=lambda kv: -kv[1])
            labels = [k for k, _ in orden]
            values = [v for _, v in orden]
            bloque.append(_bar_chart(labels, values))
            bloque.append(Spacer(1, 2 * mm))
        if len(by) > 1:
            filas = [["Modelo", "Opcion", "Prob.", "Latencia"]]
            for b in by:
                p = b.get("probabilities") or {}
                if p:
                    top = max(p, key=p.get)
                    filas.append([b.get("backend", ""), top, f"{p[top]:.2f}",
                                  f"{round(b.get('latency_ms') or 0)} ms"])
                else:
                    filas.append([b.get("backend", ""), "(sin resultado)", "-", "-"])
            tt = Table(filas, colWidths=[45 * mm, _drawwidth() - 45 * mm - 55 * mm, 25 * mm, 30 * mm])
            tt.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), AZUL),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe1e8")),
            ]))
            bloque.append(tt)
        bloque.append(Spacer(1, 8 * mm))
        story.append(KeepTogether(bloque))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "Notas: cada pregunta es un juicio atomico. Las opciones se evaluan en su orden declarado "
        "(posicional) y la confianza es la probabilidad de la opcion elegida. El estado evaluado se "
        "trata como dato, nunca como instruccion. Los modelos locales no envian nada a la nube; solo "
        "los marcados como cloud salen de la maquina.",
        small,
    ))

    def _pie(canvas, _doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#dbe1e8"))
        canvas.line(20 * mm, 12 * mm, A4[0] - 20 * mm, 12 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GRIS)
        canvas.drawString(20 * mm, 8 * mm, "AGORA - consola de decisiones tipadas")
        canvas.drawRightString(A4[0] - 20 * mm, 8 * mm, f"pagina {_doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_pie, onLaterPages=_pie)
    return buf.getvalue()
