"""Testes reais de X11, restritos a um servidor descartável.

Não são executados pela descoberta normal. Em outro terminal, abra por exemplo
``Xephyr :99 -screen 800x600 -ac -nolisten tcp`` e então execute, mantendo o
DISPLAY da sessão original:

    VIRTUAL_MOUSE_TEST_DISPLAY=:99 python3 -m unittest discover -s tests -v

O servidor :0 e o servidor da sessão atual são sempre recusados. Estes testes
injetam teclas e botões somente no servidor indicado, que deve ser descartável.
"""

import ctypes as C
import ctypes.util
import os
import re
import time
import unittest


TEST_DISPLAY = os.environ.get("VIRTUAL_MOUSE_TEST_DISPLAY")
KEY_PRESS, KEY_RELEASE, BUTTON_PRESS, BUTTON_RELEASE = 2, 3, 4, 5
XKB_USE_CORE_KBD = 0x100


class _InputEvent(C.Structure):
    _fields_ = [
        ("type", C.c_int), ("serial", C.c_ulong), ("send_event", C.c_int),
        ("display", C.c_void_p), ("window", C.c_ulong), ("root", C.c_ulong),
        ("subwindow", C.c_ulong), ("time", C.c_ulong),
        ("x", C.c_int), ("y", C.c_int), ("x_root", C.c_int), ("y_root", C.c_int),
        ("state", C.c_uint), ("detail", C.c_uint), ("same_screen", C.c_int),
    ]


class _Event(C.Union):
    _fields_ = [("type", C.c_int), ("input", _InputEvent), ("pad", C.c_long * 24)]


class _KeyboardState(C.Structure):
    _fields_ = [
        ("key_click_percent", C.c_int), ("bell_percent", C.c_int),
        ("bell_pitch", C.c_uint), ("bell_duration", C.c_uint),
        ("led_mask", C.c_ulong), ("global_auto_repeat", C.c_int),
        ("auto_repeats", C.c_ubyte * 32),
    ]


class _XkbState(C.Structure):
    _fields_ = [
        ("group", C.c_ubyte), ("locked_group", C.c_ubyte),
        ("base_group", C.c_ushort), ("latched_group", C.c_ushort),
        ("mods", C.c_ubyte), ("base_mods", C.c_ubyte),
        ("latched_mods", C.c_ubyte), ("locked_mods", C.c_ubyte),
        ("compat_state", C.c_ubyte), ("grab_mods", C.c_ubyte),
        ("compat_grab_mods", C.c_ubyte), ("lookup_mods", C.c_ubyte),
        ("compat_lookup_mods", C.c_ubyte), ("ptr_buttons", C.c_ushort),
    ]


def _local_server(display):
    match = re.fullmatch(r":(\d+)(?:\.\d+)?", display or "")
    return int(match.group(1)) if match else None


@unittest.skipUnless(TEST_DISPLAY, "defina VIRTUAL_MOUSE_TEST_DISPLAY para um X11 descartável")
class X11IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server = _local_server(TEST_DISPLAY)
        current = os.environ.get("DISPLAY", "")
        # Também reconhece :N em DISPLAYs como unix/:N e hostname:N.
        current_match = re.search(r":(\d+)(?:\.\d+)?$", current)
        current_server = int(current_match.group(1)) if current_match else None
        if server is None or server == 0 or server == current_server:
            raise RuntimeError(
                "Teste recusado: use um DISPLAY local :N, N diferente de zero "
                "e do servidor da sessão atual."
            )
        cls.x11 = C.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
        cls.xtest = C.CDLL(ctypes.util.find_library("Xtst") or "libXtst.so.6")
        cls._bind_x11()

    @classmethod
    def _bind_x11(cls):
        signatures = {
            "XOpenDisplay": ([C.c_char_p], C.c_void_p),
            "XCloseDisplay": ([C.c_void_p], C.c_int),
            "XDefaultRootWindow": ([C.c_void_p], C.c_ulong),
            "XCreateSimpleWindow": ([C.c_void_p, C.c_ulong, C.c_int, C.c_int,
                                      C.c_uint, C.c_uint, C.c_uint, C.c_ulong,
                                      C.c_ulong], C.c_ulong),
            "XDestroyWindow": ([C.c_void_p, C.c_ulong], C.c_int),
            "XMapWindow": ([C.c_void_p, C.c_ulong], C.c_int),
            "XSelectInput": ([C.c_void_p, C.c_ulong, C.c_long], C.c_int),
            "XSetInputFocus": ([C.c_void_p, C.c_ulong, C.c_int, C.c_ulong], C.c_int),
            "XGrabKey": ([C.c_void_p, C.c_int, C.c_uint, C.c_ulong,
                          C.c_int, C.c_int, C.c_int], C.c_int),
            "XUngrabKey": ([C.c_void_p, C.c_int, C.c_uint, C.c_ulong], C.c_int),
            "XWarpPointer": ([C.c_void_p, C.c_ulong, C.c_ulong, C.c_int,
                              C.c_int, C.c_uint, C.c_uint, C.c_int, C.c_int], C.c_int),
            "XQueryPointer": ([C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong),
                               C.POINTER(C.c_ulong), C.POINTER(C.c_int),
                               C.POINTER(C.c_int), C.POINTER(C.c_int),
                               C.POINTER(C.c_int), C.POINTER(C.c_uint)], C.c_int),
            "XFlush": ([C.c_void_p], C.c_int),
            "XSync": ([C.c_void_p, C.c_int], C.c_int),
            "XPending": ([C.c_void_p], C.c_int),
            "XNextEvent": ([C.c_void_p, C.POINTER(_Event)], C.c_int),
            "XKeysymToKeycode": ([C.c_void_p, C.c_ulong], C.c_ubyte),
            "XkbGetState": ([C.c_void_p, C.c_uint, C.POINTER(_XkbState)], C.c_int),
            "XkbKeysymToModifiers": ([C.c_void_p, C.c_ulong], C.c_uint),
            "XkbLockModifiers": ([C.c_void_p, C.c_uint, C.c_uint, C.c_uint], C.c_int),
            "XkbGetAutoRepeatRate": ([C.c_void_p, C.c_uint, C.POINTER(C.c_uint),
                                      C.POINTER(C.c_uint)], C.c_int),
            "XkbSetAutoRepeatRate": ([C.c_void_p, C.c_uint, C.c_uint, C.c_uint], C.c_int),
            "XGetKeyboardControl": ([C.c_void_p, C.POINTER(_KeyboardState)], C.c_int),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(cls.x11, name)
            function.argtypes = arguments
            function.restype = result
        cls.xtest.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
        cls.xtest.XTestFakeKeyEvent.restype = C.c_int

    def setUp(self):
        from virtual_mouse.x11 import X11Backend

        self.injector = self.x11.XOpenDisplay(TEST_DISPLAY.encode())
        self.assertTrue(self.injector, f"Não foi possível abrir {TEST_DISPLAY}")
        self.addCleanup(self.x11.XCloseDisplay, self.injector)
        self.receiver = self.x11.XOpenDisplay(TEST_DISPLAY.encode())
        self.assertTrue(self.receiver)
        self.addCleanup(self.x11.XCloseDisplay, self.receiver)
        self.backend = X11Backend(display_name=TEST_DISPLAY)
        self.addCleanup(self.backend.close)
        self.backend.set_enabled(False)
        self.root = self.x11.XDefaultRootWindow(self.receiver)
        self.window = self.x11.XCreateSimpleWindow(
            self.receiver, self.root, 10, 10, 320, 240, 0, 0, 0,
        )
        self.addCleanup(self.x11.XDestroyWindow, self.receiver, self.window)
        self.x11.XSelectInput(self.receiver, self.window, (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3))
        self.x11.XMapWindow(self.receiver, self.window)
        self.x11.XSetInputFocus(self.receiver, self.window, 1, 0)
        self.x11.XWarpPointer(self.receiver, 0, self.window, 0, 0, 0, 0, 120, 120)
        self.x11.XSync(self.receiver, False)
        self.held = set()
        # Registrado por último: liberar teclas antes de destruir janela/conexões.
        self.addCleanup(self._release_keys)
        self.backend_events = []
        self.window_events = []
        self.engine = None
        # Xephyr pode herdar modificadores segurados ao abrir a janela no host
        # (por exemplo, Super usado para iniciar o teste). Limpar apenas o
        # teclado do servidor DESCARTÁVEL; :0 e a sessão atual foram recusados.
        for code in self.backend.keys_down():
            self.assertTrue(self.xtest.XTestFakeKeyEvent(self.injector, code, False, 0))
        self.x11.XSync(self.injector, False)
        self._pump(0.02)
        self.backend_events.clear()
        self.window_events.clear()

    def _release_keys(self):
        for keycode in tuple(self.held):
            self.xtest.XTestFakeKeyEvent(self.injector, keycode, False, 0)
        self.x11.XFlush(self.injector)
        self.backend.set_enabled(False)
        self.x11.XSync(self.injector, False)

    def _keycode(self, keysym):
        result = self.x11.XKeysymToKeycode(self.injector, keysym)
        self.assertNotEqual(result, 0, f"Keysym ausente: {keysym:#x}")
        return result

    def _key(self, keycode, pressed):
        self.assertTrue(self.xtest.XTestFakeKeyEvent(self.injector, keycode, pressed, 0))
        if pressed:
            self.held.add(keycode)
        else:
            self.held.discard(keycode)
        self.x11.XFlush(self.injector)

    def _pump(self, duration=0.06):
        deadline = time.monotonic() + duration
        while True:
            for event in self.backend.events():
                self.backend_events.append(event)
                if self.engine and event[0] in ("press", "release"):
                    getattr(self.engine, event[0])(event[1])
            self.x11.XFlush(self.backend.display)
            while self.x11.XPending(self.receiver):
                event = _Event()
                self.x11.XNextEvent(self.receiver, C.byref(event))
                if event.type in (KEY_PRESS, KEY_RELEASE, BUTTON_PRESS, BUTTON_RELEASE):
                    self.window_events.append((event.type, event.input.detail))
            if time.monotonic() >= deadline:
                return
            time.sleep(0.002)

    def _enable_engine(self):
        from virtual_mouse.config import Settings
        from virtual_mouse.engine import MouseEngine

        self.engine = MouseEngine(self.backend, Settings())
        self.engine.set_enabled(True)
        self.addCleanup(self.engine.stop)
        self.backend.set_enabled(True)

    def _set_lock_modifier(self, keysym, enabled):
        mask = self.x11.XkbKeysymToModifiers(self.injector, keysym)
        self.assertTrue(mask, f"Keysym {keysym:#x} não possui modificador neste servidor")
        state = _XkbState()
        self.assertEqual(self.x11.XkbGetState(self.injector, XKB_USE_CORE_KBD, C.byref(state)), 0)
        self.addCleanup(self.x11.XkbLockModifiers, self.injector, XKB_USE_CORE_KBD,
                        mask, state.locked_mods & mask)
        self.assertTrue(self.x11.XkbLockModifiers(
            self.injector, XKB_USE_CORE_KBD, mask, mask if enabled else 0,
        ))
        self.x11.XSync(self.injector, False)

    def _set_numlock(self, enabled):
        self._set_lock_modifier(0xFF7F, enabled)  # Num_Lock

    def _button_mask(self):
        root, child = C.c_ulong(), C.c_ulong()
        coordinates = [C.c_int() for _ in range(4)]
        mask = C.c_uint()
        self.assertTrue(self.x11.XQueryPointer(
            self.receiver, self.root, C.byref(root), C.byref(child),
            *(C.byref(value) for value in coordinates), C.byref(mask),
        ))
        return mask.value & ((1 << 8) | (1 << 10))

    def test_left_and_right_remain_pressed_until_the_key_is_released(self):
        self._enable_engine()
        for numlock in (False, True):
            self._set_numlock(numlock)
            for symbol, button in ((0xFFB5, 1), (0xFFB0, 3)):  # KP_5 / KP_0
                with self.subTest(numlock=numlock, button=button):
                    self.window_events.clear()
                    key = self._keycode(symbol)
                    self._key(key, True)
                    self._pump()
                    self.assertEqual(self._button_mask(), 1 << (button + 7))
                    self.assertEqual(self.window_events.count((BUTTON_PRESS, button)), 1)
                    self.assertNotIn((BUTTON_RELEASE, button), self.window_events)
                    self.backend.move(10, 0)
                    self._pump()
                    self.assertEqual(self._button_mask(), 1 << (button + 7))
                    self._key(key, False)
                    self._pump()
                    self.assertEqual(self._button_mask(), 0)
                    self.assertEqual(self.window_events.count((BUTTON_RELEASE, button)), 1)

    def test_disable_releases_both_buttons_and_reenable_ignores_held_keys(self):
        self._enable_engine()
        keys = [self.backend.keycodes[action] for action in ("click_left", "click_right")]
        for key in keys:
            self._key(key, True)
        self._pump()
        self.assertEqual(self._button_mask(), (1 << 8) | (1 << 10))
        self.engine.set_enabled(False)
        self.backend.set_enabled(False)
        self._pump()
        self.assertEqual(self._button_mask(), 0)
        self.backend.set_enabled(True)
        self.engine.set_enabled(True)
        self._pump()
        self.assertEqual(self._button_mask(), 0)
        for key in keys:
            self._key(key, False)
        self._pump()
        for key in keys:
            self._key(key, True)
        self._pump()
        self.assertEqual(self._button_mask(), (1 << 8) | (1 << 10))
        for key in keys:
            self._key(key, False)
        self._pump()
        self.assertEqual(self._button_mask(), 0)

    def test_decimal_and_divide_middle_click_without_releasing_held_left(self):
        self._enable_engine()
        five = self.backend.keycodes["click_left"]
        for numlock in (False, True):
            self._set_numlock(numlock)
            for symbol in (0xFFAE, 0xFFAF):  # KP_Decimal / KP_Divide
                with self.subTest(numlock=numlock, symbol=symbol):
                    self.window_events.clear()
                    key = self._keycode(symbol)
                    self._key(five, True)
                    self._pump()
                    self._key(key, True)
                    self._pump()
                    self.assertEqual(self.window_events.count((BUTTON_PRESS, 2)), 1)
                    self.assertEqual(self.window_events.count((BUTTON_RELEASE, 2)), 1)
                    self.assertFalse(self.engine.dragging)
                    self.assertEqual(self._button_mask(), 1 << 8)
                    self.assertNotIn((BUTTON_RELEASE, 1), self.window_events)
                    self._key(key, False)
                    self._key(five, False)
                    self._pump()
                    self.assertEqual(self._button_mask(), 0)
                    self.assertEqual(self.window_events.count((BUTTON_RELEASE, 1)), 1)

    def test_numpad_zero_right_clicks_instead_of_starting_drag(self):
        self._enable_engine()
        zero = self._keycode(0xFFB0)  # KP_0, independente do mapa de actions.
        for enabled in (False, True):
            with self.subTest(numlock=enabled):
                self._set_numlock(enabled)
                self.backend_events.clear()
                self.window_events.clear()
                self._key(zero, True)
                self._pump()
                self._key(zero, False)
                self._pump()
                self.assertEqual(self.backend_events, [("press", "click_right"), ("release", "click_right")])
                self.assertEqual(self.window_events.count((BUTTON_PRESS, 3)), 1)
                self.assertEqual(self.window_events.count((BUTTON_RELEASE, 3)), 1)
                self.assertNotIn((BUTTON_PRESS, 1), self.window_events)
                self.assertFalse(self.engine.dragging)

    def _chord(self, *keycodes):
        for code in keycodes:
            self._key(code, True)
        self._pump()
        for code in reversed(keycodes):
            self._key(code, False)
        self._pump()

    def test_toggle_and_quit_hotkeys_ignore_capslock_and_numlock(self):
        control, alt = self._keycode(0xFFE3), self._keycode(0xFFE9)
        toggle, quit_key = self._keycode(ord("m")), self._keycode(ord("q"))
        for capslock, numlock in ((False, False), (False, True), (True, False), (True, True)):
            with self.subTest(capslock=capslock, numlock=numlock):
                self._set_lock_modifier(0xFFE5, capslock)  # Caps_Lock
                self._set_numlock(numlock)
                self.backend.set_enabled(False)
                self.backend_events.clear()
                self.window_events.clear()
                self._chord(control, alt, toggle)
                self.assertEqual(self.backend_events, [("toggle", None)])
                self.assertNotIn((KEY_PRESS, toggle), self.window_events)
                self.backend.set_enabled(True)
                self.backend_events.clear()
                self.window_events.clear()
                self._chord(control, alt, quit_key)
                self.assertEqual(self.backend_events, [("quit", None)])
                self.assertNotIn((KEY_PRESS, quit_key), self.window_events)

    def test_virtual_terminal_switch_shortcuts_are_rejected_without_injection(self):
        from virtual_mouse.x11 import X11Backend, X11Error

        # Ctrl+Alt+Fn pode ser consumido pelo próprio XKB para trocar de VT.
        # Validar somente a configuração: nunca injetar essas combinações.
        for modifier in ("Ctrl+Alt", "Ctrl+Alt+Shift", "Ctrl+Alt+Super"):
            for number in range(1, 13):
                hotkey = f"{modifier}+F{number}"
                for setting in ("toggle_hotkey", "quit_hotkey"):
                    with self.subTest(setting=setting, hotkey=hotkey):
                        with self.assertRaises(X11Error):
                            with X11Backend(display_name=TEST_DISPLAY, reserve_hotkeys=False,
                                            **{setting: hotkey}):
                                pass

    def test_extra_shift_does_not_trigger_ctrl_alt_hotkey(self):
        control, alt = self._keycode(0xFFE3), self._keycode(0xFFE9)
        shift, letter = self._keycode(0xFFE1), self._keycode(ord("m"))
        self._chord(control, alt, shift, letter)
        self.assertEqual(self.backend_events, [])
        self.assertIn((KEY_PRESS, letter), self.window_events)
        self._chord(control, alt, letter)
        self.assertEqual(self.backend_events, [("toggle", None)])

    def test_conflicting_keypad_grab_rolls_back_every_reserved_key(self):
        from virtual_mouse.x11 import X11Error

        # Escolher a última tecla força a falha depois de vários grabs válidos.
        conflict = list(self.backend.keycodes.values())[-1]
        self.x11.XGrabKey(self.injector, conflict, 0, self.root, False, 1, 1)
        self.x11.XSync(self.injector, False)
        self.addCleanup(self.x11.XUngrabKey, self.injector, conflict, 0, self.root)
        with self.assertRaises(X11Error):
            self.backend.set_enabled(True)
        self.assertFalse(self.backend.enabled)
        self.x11.XUngrabKey(self.injector, conflict, 0, self.root)
        self.x11.XSync(self.injector, False)
        self.backend_events.clear()
        self.window_events.clear()
        for code in set(self.backend.keycodes.values()):
            self._key(code, True)
            self._key(code, False)
            self._pump(0.02)
        self.assertEqual(self.backend_events, [])
        for code in set(self.backend.keycodes.values()):
            self.assertIn((KEY_PRESS, code), self.window_events)
        # O backend continua utilizável depois que o conflito desaparece.
        self.backend.set_enabled(True)
        self._key(self.backend.keycodes["up"], True)
        self._pump()
        self.assertIn(("press", "up"), self.backend_events)

    def test_constructor_conflict_releases_hotkeys_reserved_before_failure(self):
        from virtual_mouse.x11 import X11Backend, X11Error

        # O toggle alternativo é reservado antes de detectar o quit já ocupado.
        with self.assertRaises(X11Error):
            with X11Backend(display_name=TEST_DISPLAY, toggle_hotkey="Ctrl+Alt+n"):
                pass
        control, alt, letter = self._keycode(0xFFE3), self._keycode(0xFFE9), self._keycode(ord("n"))
        self._chord(control, alt, letter)
        self.assertIn((KEY_PRESS, letter), self.window_events)
        self.assertEqual(self.backend_events, [])
        # O handler de erros e os atalhos do backend original continuam válidos.
        self._chord(control, alt, self._keycode(ord("m")))
        self.assertEqual(self.backend_events, [("toggle", None)])

    def test_key_held_when_enabling_waits_for_release_before_clicking(self):
        keypad = self.backend.keycodes["click_left"]
        self._key(keypad, True)
        self._pump()
        self.assertIn((KEY_PRESS, keypad), self.window_events)
        self._enable_engine()
        self.assertIn(keypad, self.backend._blocked)
        self.backend_events.clear()
        self.window_events.clear()
        # Repetir o press de uma tecla ainda segurada não deve iniciar um gesto.
        self._key(keypad, True)
        self._pump()
        self.assertEqual(self.backend_events, [])
        self.assertNotIn((BUTTON_PRESS, 1), self.window_events)
        self._key(keypad, False)
        self._pump()
        self.assertNotIn(keypad, self.backend._blocked)
        self.assertEqual(self.backend_events, [])
        self._key(keypad, True)
        self._key(keypad, False)
        self._pump()
        self.assertEqual(self.backend_events, [("press", "click_left"), ("release", "click_left")])
        self.assertEqual(self.window_events.count((BUTTON_PRESS, 1)), 1)
        self.assertEqual(self.window_events.count((BUTTON_RELEASE, 1)), 1)

    def test_numlock_on_and_off_capture_only_the_keypad(self):
        keypad = self.backend.keycodes["up"]
        regular = self._keycode(ord("8"))
        self.assertNotEqual(keypad, regular)
        self.backend.set_enabled(True)
        for enabled in (False, True):
            with self.subTest(numlock=enabled):
                self._set_numlock(enabled)
                self.backend_events.clear()
                self.window_events.clear()
                self._key(keypad, True)
                self._pump()
                self._key(keypad, False)
                self._pump()
                self._key(regular, True)
                self._key(regular, False)
                self._pump()
                self.assertEqual(self.backend_events.count(("press", "up")), 1)
                self.assertIn(("release", "up"), self.backend_events)
                self.assertNotIn((KEY_PRESS, keypad), self.window_events)
                self.assertIn((KEY_PRESS, regular), self.window_events)

    def test_regular_keys_are_delivered_while_keypad_is_held(self):
        keypad = self.backend.keycodes["up"]
        regular = self._keycode(ord("a"))
        self.backend.set_enabled(True)
        self._key(keypad, True)
        self._pump()
        self.assertIn(("press", "up"), self.backend_events)
        self._key(regular, True)
        self._key(regular, False)
        self._pump()
        self.assertIn((KEY_PRESS, regular), self.window_events)
        self.assertIn((KEY_RELEASE, regular), self.window_events)
        self._key(keypad, False)
        self._pump()
        self.assertIn(("release", "up"), self.backend_events)

    def test_disabled_mode_restores_keypad_typing(self):
        keypad = self.backend.keycodes["up"]
        self.backend.set_enabled(True)
        self._key(keypad, True)
        self._pump()
        self.backend.set_enabled(False)
        self._key(keypad, False)
        self._pump()
        self.window_events.clear()
        self._key(keypad, True)
        self._key(keypad, False)
        self._pump()
        self.assertIn((KEY_PRESS, keypad), self.window_events)
        self.assertIn((KEY_RELEASE, keypad), self.window_events)

    def test_holding_click_does_not_repeat(self):
        keypad = self.backend.keycodes["click_left"]
        state = _KeyboardState()
        self.x11.XGetKeyboardControl(self.injector, C.byref(state))
        if not state.global_auto_repeat or not (state.auto_repeats[keypad // 8] & (1 << (keypad % 8))):
            self.skipTest("Autorepeat está desativado neste servidor descartável")
        delay, interval = C.c_uint(), C.c_uint()
        self.assertTrue(self.x11.XkbGetAutoRepeatRate(
            self.injector, XKB_USE_CORE_KBD, C.byref(delay), C.byref(interval),
        ))
        self.addCleanup(self.x11.XkbSetAutoRepeatRate, self.injector,
                        XKB_USE_CORE_KBD, delay.value, interval.value)
        self.assertTrue(self.x11.XkbSetAutoRepeatRate(self.injector, XKB_USE_CORE_KBD, 80, 20))
        self.x11.XSync(self.injector, False)
        self._enable_engine()
        self._key(keypad, True)
        self._pump(0.30)
        self.assertEqual(self.window_events.count((BUTTON_PRESS, 1)), 1)
        self.assertNotIn((BUTTON_RELEASE, 1), self.window_events)
        self.assertEqual(self._button_mask(), 1 << 8)
        self._key(keypad, False)
        self._pump()
        self.assertEqual(self.backend_events.count(("press", "click_left")), 1)
        self.assertEqual(self.window_events.count((BUTTON_PRESS, 1)), 1)
        self.assertEqual(self.window_events.count((BUTTON_RELEASE, 1)), 1)

    def test_fast_click_release_and_repress_are_not_lost(self):
        self._enable_engine()
        keypad = self.backend.keycodes["click_left"]
        # Todas as transições entram no servidor antes do próximo poll do backend.
        for _ in range(3):
            self._key(keypad, True)
            self._key(keypad, False)
        self._pump(0.18)
        self.assertEqual(self.backend_events.count(("press", "click_left")), 3)
        self.assertEqual(self.backend_events.count(("release", "click_left")), 3)
        self.assertEqual(self.window_events.count((BUTTON_PRESS, 1)), 3)
        self.assertEqual(self.window_events.count((BUTTON_RELEASE, 1)), 3)

    def test_shift_precision_and_real_mouse_output(self):
        shift = self._keycode(0xFFE1)  # Shift_L
        self._key(shift, True)
        self._pump()
        self.assertTrue(self.backend.precision_pressed())
        self._key(shift, False)
        self._pump()
        self.assertFalse(self.backend.precision_pressed())
        root, child = C.c_ulong(), C.c_ulong()
        x, y, window_x, window_y, state = C.c_int(), C.c_int(), C.c_int(), C.c_int(), C.c_uint()

        def pointer_position():
            self.assertTrue(self.x11.XQueryPointer(
                self.receiver, self.root, C.byref(root), C.byref(child), C.byref(x),
                C.byref(y), C.byref(window_x), C.byref(window_y), C.byref(state),
            ))
            return x.value, y.value

        before = pointer_position()
        self.backend.move(13, -9)
        self.backend.button(3, True)
        self.backend.button(3, False)
        self._enable_engine()
        for symbol, button in ((0xFFAB, 4), (0xFF8D, 5)):  # KP_Add / KP_Enter
            key = self._keycode(symbol)
            self._key(key, True)
            self._pump()
            self._key(key, False)
            self._pump()
            self.assertNotIn((KEY_PRESS, key), self.window_events)
            self.assertEqual(self.window_events.count((BUTTON_PRESS, button)), 1)
        self._pump()
        self.assertEqual(pointer_position(), (before[0] + 13, before[1] - 9))
        self.assertIn((BUTTON_PRESS, 3), self.window_events)
        self.assertIn((BUTTON_RELEASE, 3), self.window_events)
        self.assertIn((BUTTON_PRESS, 4), self.window_events)
        self.assertIn((BUTTON_PRESS, 5), self.window_events)


if __name__ == "__main__":
    unittest.main()
