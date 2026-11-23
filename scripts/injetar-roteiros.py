#!/usr/bin/env python3
"""Grava no MisterClip (andes) os roteiros de roteiros/ideias/NN-*.txt como roteiro de cada ideia (NN = número da ideia) e abre o modal de edição.
Uso: scripts/injetar-roteiros.py [NN ...]   (o token vem de token.txt, nunca é impresso)"""
import json, pathlib, sys, urllib.request

BASE = "http://100.70.97.18:8490"
ROOT = pathlib.Path(__file__).resolve().parent.parent
TOKEN = (ROOT / "token.txt").read_text().strip()
META = json.loads((ROOT / "roteiros" / "ideias" / "notas.json").read_text(encoding="utf-8"))
for extra in sorted((ROOT / "roteiros" / "ideias").glob("notas-*.json")):      # cada lote de roteiros traz as suas notas
    META.update(json.loads(extra.read_text(encoding="utf-8")))


def call(path, method="GET", body=None):
    r = urllib.request.Request(BASE + path, method=method, headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
                               data=json.dumps(body).encode() if body is not None else None)
    return json.load(urllib.request.urlopen(r, timeout=120))


cid = call("/api/channels")[0]["id"]
want = {int(a) for a in sys.argv[1:]}
for f in sorted((ROOT / "roteiros" / "ideias").glob("[0-9][0-9]-*.txt")):
    n = int(f.name[:2])
    if want and n not in want:
        continue
    notas = META[str(n)]
    r = call(f"/api/channels/{cid}/ideas/{n}/script", "PUT", {"marcado": f.read_text(encoding="utf-8"), "revisado": True, "notas": notas})
    print(n, r["palavras"], "palavras", r["minutos"], "min", [a["nivel"] for a in r["achados"]], len(r["pontos_de_saida"]), "pontos de saída")
