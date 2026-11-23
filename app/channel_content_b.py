"""Conteúdo do Arcano Digital, parte B: banco de 100 ideias ranqueadas (prompt 2) e 20 ideias com títulos, miniatura e gancho (prompt 4).

Potencial (0 a 100) = julgamento de procura na busca + diferencial frente ao que existe + vida útil + chance de virar série. Não é medição.
"""
from . import channel_plan

M = {"busca": "procura forte na busca", "dif": "diferencial raro", "serie": "episódio da série", "atual": "ligado à atualidade", "ever": "vida útil longa", "lenda": "separa história de lenda"}

# (título, categoria, potencial, motivo)
_RAW = [
    # ---- Tradições e mestres (30)
    ("Hermetismo de verdade: o que Hermes Trismegisto ensinou e o que o Caibalion não diz", "tradicoes", 95, "busca+lenda"),
    ("Alquimia: o que os alquimistas realmente buscavam (e não era ouro)", "tradicoes", 93, "busca+ever"),
    ("Os sete princípios do Caibalion: o que são e de onde vieram", "tradicoes", 92, "busca"),
    ("Os 22 arcanos maiores do tarô e a sua origem real", "tradicoes", 89, "busca+dif"),
    ("O que é a Tábua de Esmeralda: o texto verso a verso", "tradicoes", 88, "busca"),
    ("Cabala e a Árvore da Vida explicadas do zero", "tradicoes", 87, "busca"),
    ("Quem foi Eliphas Lévi, o homem que inventou o ocultismo moderno", "tradicoes", 86, "dif"),
    ("Raimundo Lúlio e a máquina de pensar do século treze", "tradicoes", 86, "dif+ponte"),
    ("Aleister Crowley sem mitos: o que Thelema diz de verdade", "tradicoes", 85, "dif+lenda"),
    ("Gnosticismo: a ideia de que o mundo é uma prisão", "tradicoes", 84, "busca"),
    ("Carl Jung e a alquimia: por que o psicólogo estudou a pedra filosofal", "tradicoes", 84, "dif"),
    ("O Corpus Hermeticum: como um livro 'egípcio' conquistou a Renascença", "tradicoes", 83, "lenda"),
    ("A Maçonaria e o ocultismo: o que a história confirma e o que é lenda", "tradicoes", 82, "busca+lenda"),
    ("John Dee: o conselheiro da rainha que falava com anjos", "tradicoes", 81, "história"),
    ("Giordano Bruno: o monge que morreu por defender um universo infinito", "tradicoes", 80, "história"),
    ("O Sefer Yetzirah: o livro que descreve a criação como um código", "tradicoes", 80, "dif"),
    ("Rosacruzes: a sociedade que talvez nunca tenha existido", "tradicoes", 79, "lenda"),
    ("Madame Blavatsky e a Teosofia: a mulher que levou o Oriente ao ocultismo ocidental", "tradicoes", 78, "história"),
    ("Astrologia: ciência antiga, tradição ou ilusão?", "tradicoes", 76, "busca"),
    ("A Golden Dawn: a ordem que reinventou a magia moderna", "tradicoes", 77, "história"),
    ("A história do tarô: da corte italiana ao ocultismo", "tradicoes", 77, "busca"),
    ("Paracelso: o médico alquimista que mudou a ciência", "tradicoes", 74, "história"),
    ("Nicolas Flamel: homem real ou invenção?", "tradicoes", 72, "lenda"),
    ("Fulcanelli: o alquimista que ninguém viu", "tradicoes", 71, "lenda"),
    ("Neoplatonismo: a filosofia que virou magia", "tradicoes", 70, "dif"),
    ("Pitágoras e a música das esferas", "tradicoes", 68, "história"),
    ("Platão e o mundo das ideias: o ocultismo escondido na filosofia", "tradicoes", 66, "dif"),
    ("A Cabala cristã: quando a Renascença leu os rabinos", "tradicoes", 65, "dif"),
    ("Jakob Boehme e a mística alemã que inspirou filósofos", "tradicoes", 62, "nicho"),
    ("Zoroastro e o dualismo: a origem do bem contra o mal", "tradicoes", 60, "história"),
    # ---- Ocultismo × tecnologia (20)
    ("Alquimia e inteligência artificial: o que a pedra filosofal tem a ver com as máquinas que pensam", "ponte", 90, "dif+atual"),
    ("O Golem de Praga: a primeira inteligência artificial da história?", "ponte", 88, "dif"),
    ("Peter Thiel, o Anticristo e a Casa Branca: o que é fato e o que é lenda", "ponte", 87, "atual+lenda"),
    ("Singularidade: a escatologia dos engenheiros", "ponte", 86, "dif"),
    ("Simulação: o gnosticismo moderno do Vale do Silício", "ponte", 85, "dif+atual"),
    ("Prompt é feitiço? A linguagem que cria coisas, de Moisés ao computador", "ponte", 85, "dif"),
    ("Transumanismo é uma religião?", "ponte", 84, "atual"),
    ("A cabala e o código: as letras que criam o mundo e o computador", "ponte", 83, "dif"),
    ("Realidade virtual e a caverna de Platão", "ponte", 80, "ever"),
    ("Deus em uma máquina: quando a IA vira oráculo", "ponte", 82, "atual"),
    ("Imortalidade digital: a alquimia do século vinte e um", "ponte", 78, "atual"),
    ("Palantir e as pedras videntes: a mitologia dentro da tecnologia", "ponte", 79, "atual"),
    ("Os alquimistas do Vale do Silício", "ponte", 77, "atual"),
    ("Kurzweil, Deus e o fim dos tempos", "ponte", 76, "atual"),
    ("Gnose digital: o misticismo escondido na cultura tech", "ponte", 75, "dif"),
    ("Tecnologia ou magia? A terceira lei de Clarke e os antigos magos", "ponte", 74, "ever"),
    ("Vigilância e o olho que tudo vê: do ocultismo ao dado", "ponte", 73, "atual"),
    ("Leibniz e o sonho da língua universal que virou computação", "ponte", 68, "dif"),
    ("Ada Lovelace e a poesia da máquina", "ponte", 65, "história"),
    ("Autômatos: dos templos de Alexandria às máquinas de pensar", "ponte", 70, "dif"),
    # ---- Filosofia como lente (14)
    ("Como estudar ocultismo sem acreditar em nada: um guia para céticos", "filosofia", 79, "dif"),
    ("O que é gnose e por que ela inquieta tanta gente", "filosofia", 74, "busca"),
    ("Nietzsche e o ocultismo: o além-do-homem como projeto mágico?", "filosofia", 72, "dif"),
    ("A morte na tradição esotérica", "filosofia", 70, "busca"),
    ("Estoicismo e hermetismo: a mesma disciplina da mente?", "filosofia", 69, "dif"),
    ("Por que as pessoas acreditam em magia", "filosofia", 68, "busca"),
    ("Símbolos: por que a mente humana precisa deles", "filosofia", 67, "ever"),
    ("Existe livre-arbítrio? O que os místicos respondiam", "filosofia", 66, "busca"),
    ("Schopenhauer e o véu de Maya", "filosofia", 65, "ever"),
    ("Mística e ciência: onde elas se separam", "filosofia", 64, "ever"),
    ("O que Platão disse sobre a alma", "filosofia", 63, "ever"),
    ("Ética na era das máquinas: o que a tradição tem a dizer", "filosofia", 60, "atual"),
    ("Atenção como prática espiritual", "filosofia", 58, "nicho"),
    ("O silêncio e a mente", "filosofia", 55, "nicho"),
    # ---- Futuro, consciência e simulação (14)
    ("A hipótese da simulação: de Platão ao Vale do Silício", "futuro", 83, "busca"),
    ("Consciência artificial: uma máquina pode ter alma?", "futuro", 82, "atual"),
    ("IA e religião: o que acontece quando a máquina fala de Deus", "futuro", 80, "atual"),
    ("O fim do mundo nos grandes sistemas: do Apocalipse aos algoritmos", "futuro", 78, "dif"),
    ("Imortalidade: a velha busca e a nova tecnologia", "futuro", 73, "busca"),
    ("Profecias e algoritmos: o futuro pode ser previsto?", "futuro", 72, "atual"),
    ("A singularidade e o milênio: a mesma esperança?", "futuro", 70, "dif"),
    ("O fim do trabalho e o sentido da vida", "futuro", 66, "atual"),
    ("Mente coletiva: a internet como inconsciente do mundo", "futuro", 62, "dif"),
    ("Cérebro e computador: a metáfora que enganou a ciência", "futuro", 61, "dif"),
    ("Cidades flutuantes e novas fronteiras: a fuga da política", "futuro", 60, "atual"),
    ("Realidade aumentada e mundos paralelos", "futuro", 57, "nicho"),
    ("Biohacking: o corpo como projeto", "futuro", 55, "atual"),
    ("O metaverso morreu? O que sobrou do sonho", "futuro", 50, "atual"),
]

# potencial dos 22 arcanos (série assinatura), na ordem O Louco... O Mundo
_ARC_SCORE = [82, 91, 80, 70, 78, 72, 83, 79, 69, 68, 75, 73, 66, 87, 74, 90, 88, 71, 84, 77, 74, 76]
_ARC_EXTRA = [("A Lua", "A Lua: deepfake, ilusão e o que a IA faz com a verdade"), ("O Sol", "O Sol: consciência, iluminação e a pergunta que a máquina não responde"),
              ("O Julgamento", "O Julgamento: o dia em que a inteligência artificial for julgada"), ("O Mundo", "O Mundo: singularidade e a ideia de unidade")]
_ARC_NAMES = ["O Louco", "O Mago", "A Sacerdotisa", "A Imperatriz", "O Imperador", "O Hierofante", "Os Enamorados", "O Carro", "A Força", "O Eremita",
              "A Roda da Fortuna", "A Justiça", "O Enforcado", "A Morte", "A Temperança", "O Diabo", "A Torre", "A Estrela", "A Lua", "O Sol", "O Julgamento", "O Mundo"]


def ideias() -> list[dict]:
    items = list(_RAW)
    titles = [t for _, t in channel_plan.ARCANOS] + [t for _, t in _ARC_EXTRA]
    for k, t in enumerate(titles):
        items.append((t, "arcanos", _ARC_SCORE[k], "serie"))
    items.sort(key=lambda x: (-x[2], x[0]))
    cal = {v["titulo"] for v in channel_plan._items()}
    out = []
    for n, (t, cat, score, why) in enumerate(items, start=1):
        out.append({"n": n, "titulo": t, "categoria": cat, "potencial": score, "motivo": why.replace("+", ", "), "no_calendario": t in cal, "status": "ideia"})
    return out


# prompt 4: 20 ideias com 3 títulos, miniatura (até 4 palavras), gancho dos primeiros 15 segundos e o motivo do clique
TITULOS = [
    {"ideia": "Hermetismo de verdade", "titulos": ["Hermetismo de verdade: o que Hermes Trismegisto ensinou e o que o Caibalion não diz", "O Caibalion mentiu sobre Hermes? A origem real do hermetismo", "Hermetismo: o que realmente existe por trás do Caibalion"],
     "thumb": "O CAIBALION MENTIU?", "gancho": "Um livro de mil novecentos e oito diz vir do antigo Egito, mas o Egito nunca o escreveu, e a história de como ele ganhou essa fama é mais interessante que a lenda.",
     "motivo": "Promete corrigir um mito que o espectador provavelmente já ouviu."},
    {"ideia": "Alquimia", "titulos": ["Alquimia: o que os alquimistas realmente buscavam (e não era ouro)", "A pedra filosofal nunca foi sobre ouro: o segredo da alquimia", "O que a alquimia tentava criar de verdade"],
     "thumb": "NÃO ERA OURO", "gancho": "Durante séculos, os maiores gênios da Europa tentaram transformar chumbo em ouro, e quase todos estavam procurando outra coisa.",
     "motivo": "Curiosidade com virada: o motivo conhecido (ouro) está errado."},
    {"ideia": "Prompt é feitiço", "titulos": ["Prompt é feitiço? A linguagem que cria coisas, de Moisés ao computador", "Por que digitar uma frase para uma IA é uma forma de magia", "O Mago do tarô e o prompt: a mesma ideia, três mil anos depois"],
     "thumb": "PROMPT É FEITIÇO?", "gancho": "Falar uma frase e ver algo surgir do nada é o sonho de todos os magos antigos, e você faz isso todos os dias.",
     "motivo": "Liga uma ação que o espectador conhece à tradição que ele não imagina."},
    {"ideia": "Golem de Praga", "titulos": ["O Golem de Praga: a primeira inteligência artificial da história?", "Um rabino criou uma máquina viva: a lenda do Golem e a IA", "Golem: o que a lenda de Praga ensina sobre a inteligência artificial"],
     "thumb": "A PRIMEIRA IA?", "gancho": "Diz a lenda que um rabino de Praga criou uma criatura sem alma que obedecia a ordens escritas, e a lição da história é a que os engenheiros de hoje temem.",
     "motivo": "Surpresa histórica e ponte clara com um tema atual."},
    {"ideia": "Tarô maiores", "titulos": ["Os 22 arcanos maiores do tarô e a sua origem real", "O tarô nunca foi sobre adivinhar: a história que ninguém conta", "De jogo de corte a oráculo: a verdadeira origem do tarô"],
     "thumb": "ORIGEM REAL DO TARÔ", "gancho": "As cartas que você associa à adivinhação começaram como um jogo de salão da Itália do século quinze, e essa não é a parte mais curiosa.",
     "motivo": "Muita gente busca tarô, e o ângulo histórico é pouco coberto."},
    {"ideia": "Peter Thiel", "titulos": ["Peter Thiel, o Anticristo e a Casa Branca: o que é fato e o que é lenda", "Peter Thiel é ocultista? A pergunta certa é outra", "A bola de cristal que vigia o mundo: Peter Thiel e Trump"],
     "thumb": "É OCULTISTA?", "gancho": "O fundador de uma empresa que vigia milhões de pessoas deu quatro palestras fechadas sobre o Anticristo, e a empresa dele leva o nome de uma bola de cristal.",
     "motivo": "Nome buscado, tensão atual e promessa de separar fato de lenda."},
    {"ideia": "Simulação e gnosticismo", "titulos": ["Gnosticismo: a ideia de que o mundo é uma prisão e por que Matrix a ressuscitou", "Vivemos numa simulação? Os gnósticos já achavam que sim", "A simulação é uma ideia de dois mil anos"],
     "thumb": "O MUNDO É PRISÃO?", "gancho": "Dois mil anos antes de qualquer computador, um grupo de cristãos concluiu que o mundo era uma falsificação, e o filme Matrix quase copiou a ideia.",
     "motivo": "Une um filme conhecido a uma tradição desconhecida."},
    {"ideia": "Eliphas Lévi", "titulos": ["Quem foi Eliphas Lévi, o homem que inventou o ocultismo moderno", "O seminarista que virou mago: a vida de Eliphas Lévi", "Eliphas Lévi e O Grande Arcano: o livro que mudou a magia"],
     "thumb": "O SEMINARISTA MAGO", "gancho": "Um seminarista francês abandonou o sacerdócio, foi preso por causa de um livro e acabou dando nome a um movimento inteiro: o ocultismo.",
     "motivo": "Trajetória pessoal com um fato forte logo na primeira frase."},
    {"ideia": "Raimundo Lúlio", "titulos": ["Raimundo Lúlio e a máquina de pensar do século treze", "O místico que sonhou com o computador setecentos anos antes", "Ars Magna: a primeira máquina de lógica era mística"],
     "thumb": "A MÁQUINA DE LÚLIO", "gancho": "Há mais de setecentos anos, um místico desenhou círculos de papel que giravam para combinar verdades, e a ideia de combinar símbolos por regras reaparece na computação.",
     "motivo": "Intriga de 'quem inventou o computador' com personagem raro."},
    {"ideia": "Crowley sem mitos", "titulos": ["Aleister Crowley sem mitos: o que Thelema diz de verdade", "Crowley foi o homem mais perverso do mundo? O que os textos dizem", "Faze o que tu queres: o que Thelema realmente significa"],
     "thumb": "CROWLEY SEM MITOS", "gancho": "A frase mais famosa de Aleister Crowley quase sempre é citada pela metade, e a metade que falta muda tudo.",
     "motivo": "Corrige uma frase que todo mundo conhece."},
    {"ideia": "Jung e a alquimia", "titulos": ["Carl Jung e a alquimia: por que o psicólogo estudou a pedra filosofal", "Jung achou a mente dentro dos manuais de alquimia", "A alquimia como espelho da alma segundo Jung"],
     "thumb": "JUNG E A ALQUIMIA", "gancho": "Um dos maiores psicólogos do século vinte passou anos lendo livros de alquimia, e o motivo não tem nada a ver com chumbo.",
     "motivo": "Une psicologia popular a ocultismo, com mistério na abertura."},
    {"ideia": "Cabala e código", "titulos": ["A cabala e o código: as letras que criam o mundo e o computador", "O Sefer Yetzirah descreve a criação como programação?", "Letras, números e criação: da cabala ao código"],
     "thumb": "A CABALA É CÓDIGO?", "gancho": "Um livro de mil e quinhentos anos afirma que o universo foi criado com letras e números, e um programador reconheceria a ideia de imediato.",
     "motivo": "Tema técnico e místico juntos, pouco comum."},
    {"ideia": "Transumanismo", "titulos": ["Transumanismo é uma religião?", "A imortalidade digital é a velha alquimia", "Quem quer viver para sempre: alquimia e tecnologia"],
     "thumb": "RELIGIÃO TECH?", "gancho": "Cientistas e empresários bilionários prometem derrotar a morte, e a promessa é quase palavra por palavra a dos alquimistas.",
     "motivo": "Debate atual com uma comparação inesperada."},
    {"ideia": "O Diabo e o algoritmo", "titulos": ["O Diabo: o algoritmo que prende a sua atenção", "A carta que descreve o seu vício em redes sociais", "O Diabo do tarô e o feed infinito"],
     "thumb": "VOCÊ ESTÁ PRESO?", "gancho": "No tarô, o Diabo é a carta das correntes que o próprio prisioneiro poderia tirar, e você as segura todas as noites.",
     "motivo": "Fala direto com o hábito do espectador."},
    {"ideia": "A Torre e a bolha", "titulos": ["A Torre: e se a bolha da IA estourar?", "A carta do colapso e o futuro da inteligência artificial", "A Torre cai: o que o tarô diz sobre as bolhas"],
     "thumb": "A TORRE VAI CAIR?", "gancho": "Toda torre construída para chegar ao céu foi derrubada na história, e a de agora chama-se inteligência artificial.",
     "motivo": "Tema de notícia com leitura simbólica forte."},
    {"ideia": "John Dee", "titulos": ["John Dee: o conselheiro da rainha que falava com anjos", "O mago da rainha Elizabeth e a linguagem dos anjos", "John Dee: ciência, magia e espionagem"],
     "thumb": "FALAVA COM ANJOS", "gancho": "O homem mais culto da Inglaterra de Elizabeth primeira aconselhava a rainha sobre navegação e jurava que conversava com anjos.",
     "motivo": "Personagem real, estranho e visualmente rico."},
    {"ideia": "Ceticismo respeitoso", "titulos": ["Como estudar ocultismo sem acreditar em nada: um guia para céticos", "É possível estudar magia sem ser crédulo?", "Ocultismo para céticos: como ler sem se enganar"],
     "thumb": "SEM ACREDITAR", "gancho": "Dá para ler os livros mais estranhos do ocultismo sem acreditar em uma linha, e é assim que os melhores historiadores fazem.",
     "motivo": "Fala direto com o espectador ideal do canal."},
    {"ideia": "Hipótese da simulação", "titulos": ["A hipótese da simulação: de Platão ao Vale do Silício", "Estamos numa simulação? A pergunta tem dois mil anos", "Simulação: o que a filosofia já disse"],
     "thumb": "ESTAMOS SIMULADOS?", "gancho": "Platão desenhou uma caverna, Descartes um demônio enganador e o Vale do Silício um computador, e todos contam a mesma história.",
     "motivo": "Tema de grande procura com um ângulo histórico."},
    {"ideia": "Consciência artificial", "titulos": ["Consciência artificial: uma máquina pode ter alma?", "A IA tem alma? O que as tradições respondem", "Máquinas que sentem: ciência, filosofia e mística"],
     "thumb": "A IA TEM ALMA?", "gancho": "Nenhum cientista sabe dizer o que é consciência, e por isso ninguém consegue afirmar que uma máquina não a terá.",
     "motivo": "Pergunta aberta e polêmica, ótima para comentários."},
    {"ideia": "Alquimia do Vale do Silício", "titulos": ["Os alquimistas do Vale do Silício", "O que os bilionários da tecnologia buscam é a pedra filosofal", "Vale do Silício: a alquimia do século vinte e um"],
     "thumb": "ALQUIMISTAS TECH", "gancho": "Os homens mais ricos do mundo investem bilhões em prolongar a vida, transformar a matéria e criar mentes, e chamam isso de ciência.",
     "motivo": "Une um tema de notícia ao fio condutor do canal."},
]
