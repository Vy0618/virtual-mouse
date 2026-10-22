"""Backend X11 nativo via ctypes: grabs seletivos + releases XI2 + XTEST.

Nunca faz grab permanente do teclado. Cada KeyPress capturado é consumido e
o grab ativo é imediatamente liberado. XI2 acompanha a liberação física sem
interceptar o restante do teclado.
"""

import ctypes as C
import os


Display = C.c_void_p
Window = C.c_ulong


class XKeyEvent(C.Structure):
    _fields_ = [
        ("type", C.c_int), ("serial", C.c_ulong), ("send_event", C.c_int),
        ("display", Display), ("window", Window), ("root", Window),
        ("subwindow", Window), ("time", C.c_ulong),
        ("x", C.c_int), ("y", C.c_int), ("x_root", C.c_int), ("y_root", C.c_int),
        ("state", C.c_uint), ("keycode", C.c_uint), ("same_screen", C.c_int),
    ]


class XGenericEventCookie(C.Structure):
    _fields_ = [
        ("type", C.c_int), ("serial", C.c_ulong), ("send_event", C.c_int),
        ("display", Display), ("extension", C.c_int), ("evtype", C.c_int),
        ("cookie", C.c_uint), ("data", C.c_void_p),
    ]


class XEvent(C.Union):
    _fields_ = [("type", C.c_int), ("xkey", XKeyEvent),
                ("xcookie", XGenericEventCookie), ("pad", C.c_long * 24)]


class XIValuatorState(C.Structure):
    _fields_ = [("mask_len", C.c_int), ("mask", C.POINTER(C.c_ubyte)),
                ("values", C.POINTER(C.c_double))]


class XIRawEvent(C.Structure):
    _fields_ = [
        ("type", C.c_int), ("serial", C.c_ulong), ("send_event", C.c_int),
        ("display", Display), ("extension", C.c_int), ("evtype", C.c_int),
        ("time", C.c_ulong), ("deviceid", C.c_int), ("sourceid", C.c_int),
        ("detail", C.c_int), ("flags", C.c_int), ("valuators", XIValuatorState),
        ("raw_values", C.POINTER(C.c_double)),
    ]


class XIEventMask(C.Structure):
    _fields_ = [("deviceid", C.c_int), ("mask_len", C.c_int),
                ("mask", C.POINTER(C.c_ubyte))]


class XModifierKeymap(C.Structure):
    _fields_ = [("max_keypermod", C.c_int), ("modifiermap", C.POINTER(C.c_ubyte))]


class XErrorEvent(C.Structure):
    _fields_ = [("type", C.c_int), ("display", Display), ("resourceid", C.c_ulong),
                ("serial", C.c_ulong), ("error_code", C.c_ubyte),
                ("request_code", C.c_ubyte), ("minor_code", C.c_ubyte)]


ERROR_HANDLER = C.CFUNCTYPE(C.c_int, Display, C.POINTER(XErrorEvent))

KEYSYMS = {
    "up": "KP_8", "down": "KP_2", "left": "KP_4", "right": "KP_6",
    "up_left": "KP_7", "up_right": "KP_9", "down_left": "KP_1", "down_right": "KP_3",
    "click_left": "KP_5", "click_right": "KP_0", "click_middle": "KP_Divide",
    "click_middle_decimal": "KP_Decimal", "scroll_up": "KP_Add", "scroll_down": "KP_Enter",
}


class X11Error(RuntimeError):
    pass


def _bind(lib, name, restype, *argtypes):
    function = getattr(lib, name)
    function.restype = restype
    function.argtypes = list(argtypes)
    return function


class X11Backend:
    def __init__(self, display_name=None, toggle_hotkey="Ctrl+Alt+m", quit_hotkey="Ctrl+Alt+q", reserve_hotkeys=True):
        if os.environ.get("XDG_SESSION_TYPE") == "wayland" and display_name is None:
            raise X11Error("Esta versão requer uma sessão X11. Na tela de login, selecione Cinnamon (Xorg).")
        self.display = None
        self.enabled = False
        self._captured = set()
        self._shortcut_down = set()
        self._blocked = set()
        self._errors = []
        self._buttons = set()
        self._keymap = (C.c_ubyte * 32)()
        try:
            self.x11 = C.CDLL("libX11.so.6")
            self.xtest = C.CDLL("libXtst.so.6")
            self.xi = C.CDLL("libXi.so.6")
        except OSError as exc:
            raise X11Error("Instale as bibliotecas: sudo apt install libx11-6 libxtst6 libxi6") from exc
        self._bind_functions()
        self.display = self.x11.XOpenDisplay(display_name.encode() if display_name else None)
        if not self.display:
            raise X11Error("Não foi possível conectar ao X11. Execute no terminal da sessão gráfica, sem sudo.")
        self._handler = ERROR_HANDLER(self._on_error)
        self._previous_handler = self.x11.XSetErrorHandler(C.cast(self._handler, C.c_void_p))
        try:
            self.root = self.x11.XDefaultRootWindow(self.display)
            self.fd = self.x11.XConnectionNumber(self.display)
            values = [C.c_int() for _ in range(4)]
            if not self.xtest.XTestQueryExtension(self.display, *(C.byref(v) for v in values)):
                raise X11Error("O servidor X11 não oferece a extensão XTEST.")
            opcode, event, error = C.c_int(), C.c_int(), C.c_int()
            if not self.x11.XQueryExtension(self.display, b"XInputExtension", C.byref(opcode), C.byref(event), C.byref(error)):
                raise X11Error("O servidor X11 não oferece XInput2.")
            self._xi_opcode = opcode.value
            major, minor = C.c_int(2), C.c_int(1)
            if self.xi.XIQueryVersion(self.display, C.byref(major), C.byref(minor)) != 0 or (major.value, minor.value) < (2, 1):
                raise X11Error("É necessário XInput 2.1 ou superior.")
            supported = C.c_int()
            if not self.x11.XkbSetDetectableAutoRepeat(self.display, 1, C.byref(supported)) or not supported.value:
                raise X11Error("O servidor não oferece detecção de repetição física de teclas.")
            # Somente releases, sem registrar o texto ou as outras teclas digitadas.
            mask_data = (C.c_ubyte * 2)(0, 1 << (14 - 8))
            mask = XIEventMask(1, 2, mask_data)  # XIAllMasterDevices, XI_RawKeyRelease
            self.xi.XISelectEvents(self.display, self.root, C.byref(mask), 1)
            self.keycodes = {action: self.keycode(symbol) for action, symbol in KEYSYMS.items()}
            if not self.keycodes["click_middle_decimal"]:
                self.keycodes["click_middle_decimal"] = self.keycode("KP_Separator")
            missing = [a for a, code in self.keycodes.items() if not code]
            if missing:
                raise X11Error(f"Teclas do numpad ausentes no layout: {', '.join(missing)}")
            self._actions = {code: action for action, code in self.keycodes.items()}
            self._shift_codes = {self.keycode("Shift_L"), self.keycode("Shift_R")} - {0}
            self._modifier_masks, self._ignored_mask = self._read_modifiers()
            toggle = self._parse_hotkey(toggle_hotkey)
            quit_key = self._parse_hotkey(quit_hotkey)
            if toggle == quit_key:
                raise X11Error("Os atalhos de ativar e encerrar devem ser diferentes.")
            if toggle[0] in self._actions or quit_key[0] in self._actions:
                raise X11Error("Use uma tecla fora do numpad para os atalhos de ativar e encerrar.")
            self._shortcuts = {toggle: "toggle", quit_key: "quit"}
            if reserve_hotkeys:
                for code, modifiers in self._shortcuts:
                    for extra in range(256):
                        if extra & ~self._ignored_mask == 0:
                            self._grab(code, modifiers | extra)
            self._check_errors("Um atalho já está sendo usado por outro programa. Altere os atalhos no JSON.")
        except BaseException:
            self.close()
            raise

    def _bind_functions(self):
        x = self.x11
        p_int = C.POINTER(C.c_int)
        _bind(x, "XOpenDisplay", Display, C.c_char_p)
        _bind(x, "XCloseDisplay", C.c_int, Display)
        _bind(x, "XDefaultRootWindow", Window, Display)
        _bind(x, "XConnectionNumber", C.c_int, Display)
        _bind(x, "XStringToKeysym", C.c_ulong, C.c_char_p)
        _bind(x, "XKeysymToKeycode", C.c_ubyte, Display, C.c_ulong)
        _bind(x, "XQueryExtension", C.c_int, Display, C.c_char_p, p_int, p_int, p_int)
        _bind(x, "XkbSetDetectableAutoRepeat", C.c_int, Display, C.c_int, p_int)
        _bind(x, "XGrabKey", C.c_int, Display, C.c_int, C.c_uint, Window, C.c_int, C.c_int, C.c_int)
        _bind(x, "XUngrabKey", C.c_int, Display, C.c_int, C.c_uint, Window)
        _bind(x, "XUngrabKeyboard", C.c_int, Display, C.c_ulong)
        _bind(x, "XPending", C.c_int, Display)
        _bind(x, "XNextEvent", C.c_int, Display, C.POINTER(XEvent))
        _bind(x, "XFlush", C.c_int, Display)
        _bind(x, "XSync", C.c_int, Display, C.c_int)
        _bind(x, "XQueryKeymap", C.c_int, Display, C.POINTER(C.c_ubyte))
        _bind(x, "XGetEventData", C.c_int, Display, C.POINTER(XGenericEventCookie))
        _bind(x, "XFreeEventData", None, Display, C.POINTER(XGenericEventCookie))
        _bind(x, "XGetModifierMapping", C.POINTER(XModifierKeymap), Display)
        _bind(x, "XFreeModifiermap", C.c_int, C.POINTER(XModifierKeymap))
        _bind(x, "XSetErrorHandler", C.c_void_p, C.c_void_p)
        _bind(self.xi, "XIQueryVersion", C.c_int, Display, p_int, p_int)
        _bind(self.xi, "XISelectEvents", C.c_int, Display, Window, C.POINTER(XIEventMask), C.c_int)
        _bind(self.xtest, "XTestQueryExtension", C.c_int, Display, p_int, p_int, p_int, p_int)
        # O header atual possui 4 argumentos, diferente de manpages antigas.
        _bind(self.xtest, "XTestFakeRelativeMotionEvent", C.c_int, Display, C.c_int, C.c_int, C.c_ulong)
        _bind(self.xtest, "XTestFakeButtonEvent", C.c_int, Display, C.c_uint, C.c_int, C.c_ulong)

    def _on_error(self, display, error):
        if display == self.display:
            self._errors.append((error.contents.error_code, error.contents.request_code))
        elif self._previous_handler:
            return ERROR_HANDLER(self._previous_handler)(display, error)
        return 0

    def _check_errors(self, message):
        self.x11.XSync(self.display, 0)
        if self._errors:
            errors, self._errors = self._errors, []
            raise X11Error(f"{message} (X11: {errors})")

    def keycode(self, symbol):
        return int(self.x11.XKeysymToKeycode(self.display, self.x11.XStringToKeysym(symbol.encode())))

    def _read_modifiers(self):
        mapping = self.x11.XGetModifierMapping(self.display)
        if not mapping:
            raise X11Error("Não foi possível consultar os modificadores do teclado.")
        try:
            masks = {}
            for name, symbols in {
                "Ctrl": ("Control_L", "Control_R"), "Alt": ("Alt_L", "Alt_R"),
                "Shift": ("Shift_L", "Shift_R"), "Super": ("Super_L", "Super_R"),
                "NumLock": ("Num_Lock",), "ScrollLock": ("Scroll_Lock",),
            }.items():
                codes = {self.keycode(s) for s in symbols} - {0}
                bits = 0
                for mod in range(8):
                    for slot in range(mapping.contents.max_keypermod):
                        if mapping.contents.modifiermap[mod * mapping.contents.max_keypermod + slot] in codes:
                            bits |= 1 << mod
                masks[name.casefold()] = bits
            ignored = 2 | masks["numlock"] | masks["scrolllock"]
            return masks, ignored
        finally:
            self.x11.XFreeModifiermap(mapping)

    def _parse_hotkey(self, text):
        parts = [part.strip() for part in text.split("+")]
        modifiers = 0
        aliases = {"control": "ctrl", "meta": "super"}
        for part in parts[:-1]:
            name = aliases.get(part.casefold(), part.casefold())
            mask = self._modifier_masks.get(name, 0) if name in ("ctrl", "alt", "shift", "super") else 0
            if not mask:
                raise X11Error(f"Modificador inválido ou ausente: {part}")
            modifiers |= mask
        symbol = parts[-1]
        if len(symbol) == 1:
            symbol = symbol.lower()
        code = self.keycode(symbol)
        if not code or not modifiers:
            raise X11Error(f"Atalho inválido: {text}. Exemplo: Ctrl+Alt+m")
        ctrl_alt = self._modifier_masks["ctrl"] | self._modifier_masks["alt"]
        if modifiers & ctrl_alt == ctrl_alt and code in {self.keycode(f"F{i}") for i in range(1, 13)}:
            raise X11Error("Ctrl+Alt+F1 até F12 são reservados para troca de terminal. Use outro atalho, como Ctrl+Alt+q.")
        return code, modifiers

    def _grab(self, code, modifiers):
        # Pointer Async; Keyboard Sync. Liberação imediata em events().
        self.x11.XGrabKey(self.display, code, modifiers, self.root, 0, 1, 0)

    def keys_down(self):
        bitmap = self._keymap
        self.x11.XQueryKeymap(self.display, bitmap)
        return {code for code in range(8, 256) if bitmap[code // 8] & (1 << (code % 8))}

    def set_enabled(self, enabled):
        enabled = bool(enabled)
        if self.enabled == enabled:
            return
        self._captured.clear()
        if enabled:
            self._blocked = self.keys_down() & self._actions.keys()
            for code in self._actions:
                self._grab(code, 1 << 15)  # AnyModifier: NumLock não altera o mapa.
            try:
                self._check_errors("Não foi possível reservar o numpad. Outro programa está usando essas teclas.")
            except X11Error:
                for code in self._actions:
                    self.x11.XUngrabKey(self.display, code, 1 << 15, self.root)
                self.x11.XUngrabKeyboard(self.display, 0)
                self.x11.XFlush(self.display)
                raise
        else:
            for code in self._actions:
                self.x11.XUngrabKey(self.display, code, 1 << 15, self.root)
            self.x11.XUngrabKeyboard(self.display, 0)
            self._blocked.clear()
        self.enabled = enabled
        self.x11.XFlush(self.display)

    def events(self):
        while self.x11.XPending(self.display):
            event = XEvent()
            self.x11.XNextEvent(self.display, C.byref(event))
            if event.type == 2:  # KeyPress de um grab que pertence a esta conexão.
                code = event.xkey.keycode
                state = event.xkey.state & 255 & ~self._ignored_mask
                # Nunca deixar o teclado congelado durante callbacks ou injeções.
                self.x11.XUngrabKeyboard(self.display, 0)
                self.x11.XFlush(self.display)
                shortcut = self._shortcuts.get((code, state))
                if shortcut:
                    if code not in self._shortcut_down:
                        self._shortcut_down.add(code)
                        yield shortcut, None
                elif self.enabled and code in self._actions and code not in self._blocked:
                    if code not in self._captured:
                        self._captured.add(code)
                        yield "press", self._actions[code]
            elif event.type == 35 and event.xcookie.extension == self._xi_opcode:
                cookie = event.xcookie
                if self.x11.XGetEventData(self.display, C.byref(cookie)):
                    released = None
                    try:
                        if cookie.evtype == 14:
                            raw = C.cast(cookie.data, C.POINTER(XIRawEvent)).contents
                            code = raw.detail
                            self._shortcut_down.discard(code)
                            self._blocked.discard(code)
                            if code in self._captured:
                                self._captured.remove(code)
                                released = self._actions[code]
                    finally:
                        self.x11.XFreeEventData(self.display, C.byref(cookie))
                    if released:
                        yield "release", released

    def pending(self):
        return bool(self.x11.XPending(self.display))

    def precision_pressed(self):
        self.x11.XQueryKeymap(self.display, self._keymap)
        return any(self._keymap[code // 8] & (1 << (code % 8)) for code in self._shift_codes)

    def move(self, dx, dy):
        self.xtest.XTestFakeRelativeMotionEvent(self.display, dx, dy, 0)
        self.x11.XFlush(self.display)

    def button(self, number, pressed):
        self.xtest.XTestFakeButtonEvent(self.display, number, bool(pressed), 0)
        if pressed:
            self._buttons.add(number)
        else:
            self._buttons.discard(number)
        self.x11.XFlush(self.display)

    def scroll(self, steps):
        for _ in range(abs(steps)):
            button = 4 if steps > 0 else 5
            self.button(button, True)
            self.button(button, False)

    def close(self):
        if not self.display:
            return
        for button in list(self._buttons):
            self.button(button, False)
        self.x11.XUngrabKeyboard(self.display, 0)
        # Somente os grabs desta conexão; os atalhos de outros apps permanecem.
        self.x11.XUngrabKey(self.display, 0, 1 << 15, self.root)
        self.x11.XSync(self.display, 0)
        self.x11.XSetErrorHandler(self._previous_handler)
        self.x11.XCloseDisplay(self.display)
        self.display = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
