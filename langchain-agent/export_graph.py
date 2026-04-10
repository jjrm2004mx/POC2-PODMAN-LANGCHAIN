"""
export_graph.py — Exporta el grafo del agente como imagen PNG y Mermaid.
Uso desde WSL (dentro del contenedor o con dependencias instaladas):

  python langchain-agent/export_graph.py

Genera:
  docs/agent_graph.png     — Imagen PNG del grafo
  docs/agent_graph.mmd     — Definición Mermaid (editable / importable)
"""

import os
import sys

# Asegurar que el path del agente esté disponible
sys.path.insert(0, os.path.dirname(__file__))

from agent import agent

OUTPUT_PNG = os.path.join(os.path.dirname(__file__), "../docs/agent_graph.png")
OUTPUT_MMD = os.path.join(os.path.dirname(__file__), "../docs/agent_graph.mmd")

def export_png():
    try:
        png_bytes = agent.get_graph().draw_mermaid_png()
        with open(OUTPUT_PNG, "wb") as f:
            f.write(png_bytes)
        print(f"[OK] PNG exportado: {OUTPUT_PNG}")
    except Exception as e:
        print(f"[WARN] No se pudo exportar PNG (requiere graphviz o playwright): {e}")
        print("       Usa el archivo .mmd para visualizar en https://mermaid.live")

def export_mermaid():
    try:
        mmd = agent.get_graph().draw_mermaid()
        with open(OUTPUT_MMD, "w", encoding="utf-8") as f:
            f.write(mmd)
        print(f"[OK] Mermaid exportado: {OUTPUT_MMD}")
        print(f"\n--- Mermaid source ---\n{mmd}\n----------------------")
    except Exception as e:
        print(f"[ERROR] No se pudo exportar Mermaid: {e}")

if __name__ == "__main__":
    export_mermaid()
    export_png()
