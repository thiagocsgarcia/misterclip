#!/usr/bin/env python3
"""Inclui geopolítica no segmento do canal: pilar, categoria, promessa, ideias (com a procura medida no YouTube) e o estudo.
Uso: scripts/aplicar-geopolitica.py [URL_BASE]   (padrão: andes; o token vem de token.txt e nunca é impresso)"""
import json, pathlib, sys, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://100.70.97.18:8490"
TOKEN = (ROOT / "token.txt").read_text().strip() if "100.70.97.18" in BASE else ""


def call(path, method="GET", body=None):
    h = {"Content-Type": "application/json"}
    if TOKEN:
        h["Authorization"] = "Bearer " + TOKEN
    r = urllib.request.Request(BASE + path, method=method, headers=h, data=json.dumps(body).encode() if body is not None else None)
    return json.load(urllib.request.urlopen(r, timeout=120))


# (título, potencial, motivo)
IDEIAS = [
    ("Taiwan e a TSMC: a ilha que segura o mundo dos chips", 92, "geopolítica; um vídeo explicativo sobre Taiwan passa de 6 milhões de views"),
    ("Terras raras: o novo petróleo da inteligência artificial", 90, "geopolítica; vídeos sobre terras raras e o Brasil passam de 2 a 5 milhões de views"),
    ("A Armadilha de Tucídides: EUA e China estão condenados à guerra?", 90, "filosofia + geopolítica; a palestra de Graham Allison passa de 2,6 milhões de views"),
    ("A guerra dos chips: por que a IA virou campo de batalha entre EUA e China", 90, "geopolítica + tecnologia; reportagem em português passa de 1,7 milhão de views"),
    ("Estreito de Ormuz: onde a economia mundial prende a respiração", 88, "geopolítica; vídeos em português passam de 2 milhões de views"),
    ("Cabos submarinos: a internet vive no fundo do mar (e na mira dos governos)", 86, "geopolítica + tecnologia; o tema soma centenas de milhares de views e quase ninguém explica com calma"),
    ("O mapa de 1904 que explica as guerras: Mackinder e o Heartland", 86, "geopolítica; um vídeo passa de 1 milhão de views e o tema é ideia de autor, citável"),
    ("Brasil entre gigantes: soberania, terras raras e inteligência artificial", 84, "geopolítica; público brasileiro e ligação direta com o pilar de poder"),
    ("Fim do dólar? O que a desdolarização realmente significa", 84, "geopolítica; vídeos passam de 600 a 700 mil views"),
    ("Sun Tzu e a guerra híbrida: estratégia antiga em conflitos de hoje", 82, "tradições + geopolítica; ponte entre texto clássico e atualidade"),
    ("Ártico: a nova fronteira do poder mundial", 82, "geopolítica; vídeos passam de 1,2 milhão de views"),
    ("Satélites, espaço e guerra: quem manda na órbita?", 80, "geopolítica + tecnologia; tema em alta, de 50 a 260 mil views"),
    ("Rota da Seda: poder por estrada, porto e cabo", 80, "geopolítica; reportagem passa de 600 mil views"),
    ("Dugin e o eurasianismo: a filosofia que dizem inspirar a Rússia", 80, "geopolítica + filosofia; de 90 a 240 mil views; exige os dois lados e citação"),
    ("BRICS: mundo multipolar ou promessa exagerada?", 78, "geopolítica; de 50 a 260 mil views; tema com visões opostas, bom para o formato dos dois lados"),
    ("Haushofer e a geopolítica alemã: a ciência que virou ideologia?", 76, "geopolítica + ocultismo; liga a Thule e o mito ao que a história comprova; pouca concorrência"),
    ("Água, grãos e energia: os recursos que podem decidir o século", 76, "geopolítica; tema amplo de longa vida útil"),
]

cid = call("/api/channels")[0]["id"]
plan = call(f"/api/channels/{cid}")["plan"]

# 1) pilar novo e pesos (somam 100)
pil = [p for p in plan["pilares"] if p["id"] != "geopolitica"]
pesos = {"poder": 25, "tradicoes": 20, "arcanos": 20, "ponte": 10, "filosofia": 5}
for p in pil:
    if p["id"] in pesos:
        p["peso"] = pesos[p["id"]]
pil.append({"id": "geopolitica", "nome": "Geopolítica e poder global", "peso": 20, "papel": "Tema de maior procura depois de poder e tecnologia",
            "texto": "Chips, terras raras, cabos, rotas, moedas e as ideias que explicam a disputa entre países: Taiwan e a TSMC, a guerra dos chips, Ormuz, o Ártico, o dólar, Mackinder, Sun Tzu, a Armadilha de Tucídides. "
                     "É onde há muita audiência em português: vídeos sobre Taiwan passam de 6 milhões de views, terras raras de 2 a 5 milhões, Ormuz de 2 milhões (busca no YouTube em 22/11/2026). "
                     "O canal entra com o que os outros não têm: a lente de ideias antigas (Tucídides, Sun Tzu, Maquiavel) e a fonte dita em voz alta. Regras: descreve o interesse de cada país com os dados dele, não toma lado em guerra, "
                     "não generaliza povos, mostra fronteira em disputa como disputada e dá a data de cada número."})
assert sum(p["peso"] for p in pil) == 100, [(p["id"], p["peso"]) for p in pil]
call(f"/api/channels/{cid}/plan/pilares", "PUT", {"value": pil})

# 2) categoria do banco de ideias
nicho = plan["nicho"]
cats = [c for c in nicho.get("categorias", []) if c["id"] != "geopolitica"]
cats.append({"id": "geopolitica", "nome": "Geopolítica e poder global", "descricao": "A disputa entre países por chips, minerais, rotas, moedas e ideias, sem tomar lado e com fonte e data.",
             "exemplos": "Taiwan e a TSMC, terras raras, Armadilha de Tucídides, Ormuz"})
nicho["categorias"] = cats
call(f"/api/channels/{cid}/plan/nicho", "PUT", {"value": nicho})

# 3) promessa e público
pos = plan["posicionamento"]
if "geopolítica" not in pos["promessa"]:
    pos["promessa"] = pos["promessa"].replace("quem manda nas máquinas hoje.", "quem manda nas máquinas hoje, e como o poder se reorganiza entre os países (geopolítica de chips, minerais, rotas e moedas).")
    pos["publico"] = pos["publico"].replace("filosofia, política e tecnologia", "filosofia, política, geopolítica e tecnologia")
call(f"/api/channels/{cid}/plan/posicionamento", "PUT", {"value": pos})

# 4) ideias novas (sem repetir título), no fim da lista
ideias = plan["ideias"]
have = {i["titulo"] for i in ideias}
n = max(i["n"] for i in ideias)
for t, pot, why in IDEIAS:
    if t not in have:
        n += 1
        ideias.append({"n": n, "titulo": t, "categoria": "geopolitica", "potencial": pot, "motivo": why, "no_calendario": False, "status": "ideia"})
call(f"/api/channels/{cid}/plan/ideias", "PUT", {"value": [{k: v for k, v in i.items() if k != "roteiro"} for i in ideias]})

# 5) estudo
est = plan.get("estudo_de_temas") or {}
est["geopolitica"] = {"data": "22/11/2026", "como_foi_feito": "Busca no YouTube em português, ordenada por visualizações, para 16 temas de geopolítica ligados a tecnologia, poder e ideias.",
                      "achados": ["Taiwan e os chips: o melhor resultado passa de 6,5 milhões de views.", "Terras raras: de 2,7 a 5 milhões de views, com forte interesse brasileiro.",
                                  "Ormuz: dois vídeos acima de 2 milhões; cabos submarinos de Ormuz, 500 mil.", "Armadilha de Tucídides: 2,6 milhões (palestra de Graham Allison).",
                                  "Mackinder e o Heartland: de 190 mil a 1 milhão. Dugin e o eurasianismo: de 90 a 240 mil. Haushofer: pouca concorrência em português.",
                                  "Ártico: acima de 1 milhão. Desdolarização: de 400 a 700 mil. BRICS e Rota da Seda: de 50 a 660 mil."],
                      "limites": "São visualizações públicas dos melhores resultados na data; não mostram tempo assistido nem CTR. Muitos vídeos de geopolítica são de notícia quente e envelhecem rápido: o canal aposta em explicações de longa vida (chips, minerais, ideias)."}
call(f"/api/channels/{cid}/plan/estudo_de_temas", "PUT", {"value": est})
v = call(f"/api/channels/{cid}")["plan"]
print(len(v["ideias"]), "ideias;", [(p["id"], p["peso"]) for p in v["pilares"]])
