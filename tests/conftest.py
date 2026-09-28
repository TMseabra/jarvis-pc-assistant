"""Os testes não usam a configuração pessoal (.env): nada de abrir o Opera, etc."""

import os

# Antes de importar o jarvis: o load_dotenv não substitui variáveis que já existem.
os.environ["JARVIS_BROWSER"] = "default"
os.environ["JARVIS_PROVIDER"] = "ollama"
os.environ["JARVIS_MESSAGING"] = "web"
