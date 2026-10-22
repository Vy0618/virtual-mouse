# Contribuir / Contributing

## Português

Abra uma issue para relatar um erro ou propor uma mudança. Inclua a distribuição,
o ambiente gráfico, a versão do Python e os passos para reproduzir o problema.

Para desenvolver, use Python 3.10+ e mantenha o programa sem dependências Python
de execução, sem interface gráfica e sem polling em repouso.

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q virtual_mouse tests run.py
bash -n iniciar.sh
```

Mudanças no teclado ou no mouse devem ser validadas também em um X11 descartável.
Veja as instruções em [tests/test_x11_integration.py](tests/test_x11_integration.py).
O CI usa Xvfb para executar esses testes sem controlar o desktop de quem contribui.

Mantenha a liberação dos botões ao desativar/encerrar e a compatibilidade com Num
Lock. Adicione testes para comportamentos novos e atualize os dois idiomas do
[README](README.md) quando alterar comandos ou teclas. Descreva na PR o resultado
da mudança e como ela foi validada.

## English

Open an issue to report a bug or propose a change. Include your Linux distribution,
desktop environment, Python version, and reproduction steps.

Use Python 3.10+ for development. Keep the application free of runtime Python
dependencies, graphical interfaces, and idle polling.

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q virtual_mouse tests run.py
bash -n iniciar.sh
```

Keyboard and mouse changes should also be tested on a disposable X11 server.
See [tests/test_x11_integration.py](tests/test_x11_integration.py) for instructions.
CI uses Xvfb to run these tests without controlling a contributor's desktop.

Preserve button release on disable/exit and Num Lock compatibility. Add tests for
new behavior and update both languages in the [README](README.md) when changing
commands or keys. Describe the resulting behavior and validation in your PR.
