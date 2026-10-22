# Virtual Mouse / Mouse Virtual

[Português](#português) | [English](#english)

[Contribuir / Contributing](CONTRIBUTING.md) · [Publicar / Publishing](PUBLISHING.md)

## Português

Controle o mouse pelo teclado numérico, sem interface gráfica.

### Instalação

Requer **Linux com sessão X11**, Python 3.10+ e teclado numérico. Validado no
Linux Mint 22.3. Não funciona em sessões Wayland.

Instale as dependências:

```bash
sudo apt install python3 libx11-6 libxtst6 libxi6
```

Na pasta do projeto:

```bash
chmod +x iniciar.sh
./iniciar.sh
```

Execute como seu usuário, sem `sudo`. Não precisa de pip nem de acesso a
`/dev/input`. Também pode executar com `python3 run.py`.

### Uso e atalho no i3wm

O programa inicia **desativado**. Use `Ctrl+Alt+M` para ativar/desativar e
`Ctrl+Alt+Q` para encerrar. No terminal, `Ctrl+C` também encerra.

```bash
./iniciar.sh --enabled   # Iniciar ativado
./iniciar.sh --toggle    # Iniciar ativado ou alternar a instância existente
```

Para usar pelo i3, adicione em `~/.config/i3/config`, ajustando o caminho:

```i3
bindsym --release $mod+F8 exec --no-startup-id /caminho/absoluto/virtual_mouse/iniciar.sh --toggle
```

Recarregue com `$mod+Shift+c`, se usar o atalho padrão do i3.
Com `$mod` definido como `Mod4`, o atalho será **Win+F8**:

- Primeiro uso: inicia o programa ativado, sem abrir terminal.
- Próximos usos: desativa/ativa a mesma instância.
- Desativado: o processo fica em espera e o numpad volta ao normal.
- `Ctrl+Alt+Q`: encerra o processo.

Não é necessário iniciar o programa junto com o i3. Veja [i3.conf.example](i3.conf.example).
No terminal, a primeira execução com `--toggle` permanece em primeiro plano.

### Função de cada tecla

As teclas abaixo são do **numpad**, na disposição de um teclado numérico.

<table align="center">
  <tr>
    <td align="center"><b>Num</b><br>Num Lock</td>
    <td align="center"><b>/</b><br>Clique do meio</td>
    <td align="center"><b>*</b><br>Função normal</td>
    <td align="center"><b>-</b><br>Função normal</td>
  </tr>
  <tr>
    <td align="center"><b>7</b><br>↖</td>
    <td align="center"><b>8</b><br>↑</td>
    <td align="center"><b>9</b><br>↗</td>
    <td align="center" rowspan="2"><b>+</b><br>Scroll para cima</td>
  </tr>
  <tr>
    <td align="center"><b>4</b><br>←</td>
    <td align="center"><b>5</b><br>Clique esquerdo<br>Segure para manter</td>
    <td align="center"><b>6</b><br>→</td>
  </tr>
  <tr>
    <td align="center"><b>1</b><br>↙</td>
    <td align="center"><b>2</b><br>↓</td>
    <td align="center"><b>3</b><br>↘</td>
    <td align="center" rowspan="2"><b>Enter</b><br>Scroll para baixo</td>
  </tr>
  <tr>
    <td align="center" colspan="2"><b>0</b><br>Clique direito<br>Segure para manter</td>
    <td align="center"><b>. ou ,</b><br>Clique do meio</td>
  </tr>
</table>

Mantenha `+` ou `Enter` pressionado para rolagem contínua.

| Modificador ou atalho | Função |
| --- | --- |
| `Shift` | Reduzir a velocidade do cursor para maior precisão |
| `Ctrl+Alt+M` | Ativar/desativar o controle |
| `Ctrl+Alt+Q` | Encerrar o programa |

Um toque rápido em `5` ou `0` faz um clique normal. Para arrastar, segure o botão
desejado e use as direções. Os dois botões podem ser segurados ao mesmo tempo.
O decimal e `/` fazem clique do meio; para arrastar, mantenha `5` ou `0` pressionado.

Num Lock pode ficar ligado ou desligado. O Enter comum, `-`, `*` e os números da
fileira superior mantêm suas funções normais. Shift também mantém seu efeito
normal como modificador de cliques.

### Configuração

Crie o arquivo padrão:

```bash
./iniciar.sh --write-config
```

Edite `~/.config/virtual-mouse/config.json`. Se `XDG_CONFIG_HOME` estiver definido,
o caminho será `$XDG_CONFIG_HOME/virtual-mouse/config.json`.
O comando não sobrescreve um arquivo existente. Sem arquivo, o programa usa os padrões.

Ajustes mais comuns: `speed` (pixels/segundo), `precision_factor` (velocidade
com Shift) e `scroll_interval` (intervalo da rolagem em segundos).

**[config.example.json](config.example.json) é apenas um modelo.** Para carregar
esse arquivo diretamente:

```bash
./iniciar.sh --config ./config.example.json
```

As opções do JSON ajustam velocidade, comportamento e atalhos de controle;
o mapeamento das teclas do numpad está em `virtual_mouse/x11.py`.
Após editar a configuração ou atualizar o código, encerre com `Ctrl+Alt+Q` e
inicie novamente. `--toggle` não recarrega a configuração da instância existente.

### Funcionamento e arquitetura

O programa recebe os eventos do teclado pelo X11 e transforma as teclas em ações
do mouse. Segurar uma direção mantém o movimento, com aceleração gradual;
as diagonais têm a mesma velocidade das outras direções.

Usa um único processo, sem threads. Parado, espera eventos; durante movimento
ou rolagem, atualiza a 60 Hz por padrão. Segurar um clique não exige atualizações
periódicas. Desativar ou encerrar libera os botões. Teclas já pressionadas na
ativação precisam ser soltas antes de um novo uso.

| Arquivo | Responsabilidade |
| --- | --- |
| `iniciar.sh`, `run.py`, `virtual_mouse/__main__.py` | Pontos de entrada |
| `virtual_mouse/app.py` | Comandos, loop de eventos, ativação e encerramento |
| `virtual_mouse/engine.py` | Movimento, aceleração, cliques mantidos, arraste e scroll |
| `virtual_mouse/x11.py` | Captura do numpad, liberação de teclas via XInput2 e saída via XTEST |
| `virtual_mouse/control.py` | Comunicação local por socket para o `--toggle`, por usuário/display |
| `virtual_mouse/config.py` | Leitura, validação e gravação do JSON |
| `tests/` | Testes de comportamento e integração X11 |

### Diagnóstico e testes

```bash
./iniciar.sh --check
python3 -m unittest discover -s tests -v
```

`--check` verifica o X11 sem mover o cursor nem reservar teclas. Testes de
integração precisam de um X11 descartável; as instruções estão em
[tests/test_x11_integration.py](tests/test_x11_integration.py).

---

## English

Control the mouse with the numeric keypad, without a graphical interface.

### Setup

Requires **Linux running an X11 session**, Python 3.10+, and a numeric keypad.
Validated on Linux Mint 22.3. Wayland sessions are not supported.

Install the dependencies:

```bash
sudo apt install python3 libx11-6 libxtst6 libxi6
```

From the project folder:

```bash
chmod +x iniciar.sh
./iniciar.sh
```

Run as your regular user, without `sudo`. No pip packages or `/dev/input` access
are needed. You can also run `python3 run.py`.

### Usage and i3wm shortcut

The program starts **disabled**. Press `Ctrl+Alt+M` to enable/disable it and
`Ctrl+Alt+Q` to quit. When running in a terminal, `Ctrl+C` also quits.

```bash
./iniciar.sh --enabled   # Start enabled
./iniciar.sh --toggle    # Start enabled or toggle the existing instance
```

To use it from i3, add this to `~/.config/i3/config`, adjusting the path:

```i3
bindsym --release $mod+F8 exec --no-startup-id /absolute/path/virtual_mouse/iniciar.sh --toggle
```

Reload with `$mod+Shift+c` if you use the default i3 reload binding.
With `$mod` set to `Mod4`, the shortcut is **Super/Windows+F8**:

- First use: starts the program enabled, without opening a terminal.
- Later uses: disables/enables the same instance.
- Disabled: the process waits for events and the keypad works normally.
- `Ctrl+Alt+Q`: exits the process.

No i3 autostart entry is needed. See [i3.conf.example](i3.conf.example).
In a terminal, the first `--toggle` invocation stays in the foreground.

### Key mapping

The table follows the physical layout of the **numeric keypad**.

<table align="center">
  <tr>
    <td align="center"><b>Num</b><br>Num Lock</td>
    <td align="center"><b>/</b><br>Middle Click</td>
    <td align="center"><b>*</b><br>Normal Function</td>
    <td align="center"><b>-</b><br>Normal Function</td>
  </tr>
  <tr>
    <td align="center"><b>7</b><br>↖</td>
    <td align="center"><b>8</b><br>↑</td>
    <td align="center"><b>9</b><br>↗</td>
    <td align="center" rowspan="2"><b>+</b><br>Scroll Up</td>
  </tr>
  <tr>
    <td align="center"><b>4</b><br>←</td>
    <td align="center"><b>5</b><br>Left Click<br>Hold to Keep Pressed</td>
    <td align="center"><b>6</b><br>→</td>
  </tr>
  <tr>
    <td align="center"><b>1</b><br>↙</td>
    <td align="center"><b>2</b><br>↓</td>
    <td align="center"><b>3</b><br>↘</td>
    <td align="center" rowspan="2"><b>Enter</b><br>Scroll Down</td>
  </tr>
  <tr>
    <td align="center" colspan="2"><b>0</b><br>Right Click<br>Hold to Keep Pressed</td>
    <td align="center"><b>. or ,</b><br>Middle Click</td>
  </tr>
</table>

Hold `+` or keypad `Enter` to keep scrolling.

| Modifier or shortcut | Function |
| --- | --- |
| `Shift` | Slow down cursor movement for precision |
| `Ctrl+Alt+M` | Enable/disable control |
| `Ctrl+Alt+Q` | Quit the program |

A quick tap on `5` or `0` performs a normal click. To drag, hold the desired
button key and use the direction keys. Both buttons can be held simultaneously.
Decimal and `/` perform a middle click; hold `5` or `0` to drag.

Num Lock can be on or off. Regular Enter, `-`, `*`, and the top-row number keys
keep their normal functions. Shift also retains its normal effect as a click modifier.

### Configuration

Create the default configuration file:

```bash
./iniciar.sh --write-config
```

Edit `~/.config/virtual-mouse/config.json`. When `XDG_CONFIG_HOME` is set,
the path is `$XDG_CONFIG_HOME/virtual-mouse/config.json`.
The command will not overwrite an existing file. Without a file, defaults apply.

Common settings: `speed` (pixels/second), `precision_factor` (speed multiplier
with Shift), and `scroll_interval` (scrolling interval in seconds).

**[config.example.json](config.example.json) is only a template.** To load it directly:

```bash
./iniciar.sh --config ./config.example.json
```

JSON options configure speed, behavior, and control shortcuts; the keypad mapping
is defined in `virtual_mouse/x11.py`. After editing configuration or updating the
code, quit with `Ctrl+Alt+Q` and start again. `--toggle` does not reload settings
for an existing instance.

### How it works and architecture

The program receives X11 keyboard events and converts keys into mouse actions.
Holding a direction keeps the cursor moving, with gradual acceleration;
diagonal movement has the same speed as other directions.

It uses one process and no threads. While idle, it waits for events; during
movement or scrolling, updates run at 60 Hz by default. Holding a click does
not require periodic updates. Disabling or quitting releases the buttons.
Keys already held when enabling control must be released before being used again.

| File | Responsibility |
| --- | --- |
| `iniciar.sh`, `run.py`, `virtual_mouse/__main__.py` | Entry points |
| `virtual_mouse/app.py` | Commands, event loop, activation, and shutdown |
| `virtual_mouse/engine.py` | Movement, acceleration, held clicks, drag, and scrolling |
| `virtual_mouse/x11.py` | Keypad capture, key releases through XInput2, and mouse output through XTEST |
| `virtual_mouse/control.py` | Local socket communication for `--toggle`, per user/display |
| `virtual_mouse/config.py` | JSON loading, validation, and saving |
| `tests/` | Behavior tests and X11 integration tests |

### Diagnostics and tests

```bash
./iniciar.sh --check
python3 -m unittest discover -s tests -v
```

`--check` verifies X11 without moving the cursor or reserving keys. Integration
tests require a disposable X11 server; see
[tests/test_x11_integration.py](tests/test_x11_integration.py) for instructions.
