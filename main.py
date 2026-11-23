from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
import queue
import random
import time
import pydirectinput as direct
import sounddevice as sd
import vosk
import sys



direct.PAUSE = 0.005

# --- РАСЧЁТ ПОВОРОТА ---
print("=== CS2 Voice Control ===")
sens_input = input("Введите значение sensitivity из настроек CS2 (Enter = 1.5): ").strip().replace(",", ".")
try:
    CS2_SENSITIVITY = float(sens_input) if sens_input else 1.5
except ValueError:
    CS2_SENSITIVITY = 1.5

PIXELS_PER_DEGREE = 1.0 / (0.022 * CS2_SENSITIVITY)
print(f"Чувствительность: {CS2_SENSITIVITY} | Масштаб: {PIXELS_PER_DEGREE:.2f} пикс/град.\n")


BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
model = vosk.Model(os.path.join(BASE_DIR, "vosk-model-small-ru-0.22"))


words = (
    '["прямо", "стой", "назад", "лево", "право", '
    '"налево", "направо", "вверх", "вниз", "разворот", "веди", "быстро", '
    '"огонь", "очередь", "стреляй", "прицел", "прыжок", '
    '"ползи", "встань", "тихо", "бегом", '
    '"винтовка", "пистолет", "нож", "зевс", "бомба", "граната", "флешка", "дым", "молотов", '
    '"перезарядка", "обойма", "сброс", "закуп", "закрыть", "купить", "столб", "слот", '
    '"полсекунды", "четверть", "секунды", '
    '"один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять", "десять", '
    '"пятнадцать", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто", "сто", '
    '"за", "зачем", "ну", "так", "вот", "[unk]"]'
)
recognizer = vosk.KaldiRecognizer(model, 16000, words)

NUMBERS = {"один": "1", "два": "2", "три": "3", "четыре": "4", "пять": "5"}

COUNTS = {
    "один": 1, "два": 2, "три": 3, "четыре": 4, "пять": 5,
    "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
    "пятнадцать": 15, "двадцать": 20, "тридцать": 30, "сорок": 40,
    "пятьдесят": 50, "шестьдесят": 60, "семьдесят": 70,
    "восемьдесят": 80, "девяносто": 90, "сто": 100,
}

DURATIONS = {
    "четверть": 0.25, "полсекунды": 0.5, "один": 1.0, "два": 2.0, "три": 3.0,
    "четыре": 4.0, "пять": 5.0, "шесть": 6.0, "семь": 7.0, "восемь": 8.0,
    "девять": 9.0, "десять": 10.0, "пятнадцать": 15.0, "двадцать": 20.0, "тридцать": 30.0,
}

INSTANT_COMMANDS = {
    "стой", "назад", "лево", "право", "огонь", "очередь", "прицел",
    "встань", "тихо", "бегом", "перезарядка", "обойма", "сброс", "закуп", "закрыть",
    "винтовка", "пистолет", "нож", "зевс", "бомба", "граната", "флешка", "дым", "молотов"
}

q = queue.Queue()
executor = ThreadPoolExecutor(max_workers=6)
ignore_until = 0
last_partial = ""
partial_hits = 0
last_partial_change = 0
is_running_forward = False
is_crouching = False
is_tracking = False

def callback(indata, frames, time_info, status):
    q.put(bytes(indata))

def human_sleep(min_sec, max_sec):
    time.sleep(random.uniform(min_sec, max_sec))

def tap(key):
    direct.keyDown(key)
    human_sleep(0.035, 0.075)
    direct.keyUp(key)

def human_click(button="left"):
    direct.mouseDown(button=button)
    human_sleep(0.035, 0.065)
    direct.mouseUp(button=button)

def buy(cat, slot):
    tap(cat)
    human_sleep(0.07, 0.13)
    tap(slot)

def parse_number_words(word_args, default_val):
    if not word_args:
        return default_val
    total = 0
    found = False
    for w in word_args:
        if w in COUNTS:
            total += COUNTS.get(w, 0)
            found = True
    return total if found else default_val

def human_move_camera(deg_x=0, deg_y=0):
    target_dx = round(deg_x * PIXELS_PER_DEGREE * random.uniform(0.985, 1.015))
    target_dy = round(deg_y * PIXELS_PER_DEGREE * random.uniform(0.985, 1.015))
    total_dist = math.hypot(target_dx, target_dy)
    if total_dist < 1:
        return
    steps = max(8, min(32, int(total_dist / 45) + random.randint(6, 10)))
    moved_x = 0
    moved_y = 0
    for i in range(1, steps + 1):
        progress = 0.5 * (1 - math.cos(math.pi * i / steps))
        cur_x = round(target_dx * progress)
        cur_y = round(target_dy * progress)
        step_x = cur_x - moved_x
        step_y = cur_y - moved_y
        moved_x = cur_x
        moved_y = cur_y
        if step_x != 0 or step_y != 0:
            direct.moveRel(step_x, step_y, relative=True)
        human_sleep(0.008, 0.015)
def run_command(text):
    global is_running_forward, is_crouching, is_tracking
    print("Выполняю:", text)
    parts = text.split()
    cmd, *args = parts

    if text == "стой":
        is_running_forward = False
        is_crouching = False
        is_tracking = False
        for key in ("w", "s", "a", "d", "ctrl", "shift"):
            direct.keyUp(key)
            human_sleep(0.005, 0.015)

    elif cmd == "налево":
        deg = parse_number_words(args, 45)
        human_move_camera(deg_x=-deg, deg_y=0)

    elif cmd == "направо":
        deg = parse_number_words(args, 45)
        human_move_camera(deg_x=deg, deg_y=0)

    elif cmd == "вверх":
        deg = parse_number_words(args, 15)
        human_move_camera(deg_x=0, deg_y=-deg)

    elif cmd == "вниз":
        deg = parse_number_words(args, 15)
        human_move_camera(deg_x=0, deg_y=deg)

    elif text == "разворот":
        direction = random.choice((-1, 1))
        human_move_camera(deg_x=180 * direction, deg_y=0)

    elif cmd == "веди":
        is_tracking = False
        time.sleep(0.03)
        speed_deg_per_sec = 70.0 if "быстро" in args else 35.0
        direction = 0
        if "лево" in args or "налево" in args:
            direction = -1
        elif "право" in args or "направо" in args:
            direction = 1

        if direction != 0:
            is_tracking = True
            acc_x = 0.0
            while is_tracking:
                dt = random.uniform(0.014, 0.022)
                acc_x += speed_deg_per_sec * PIXELS_PER_DEGREE * dt * direction
                step_x = int(acc_x)
                if step_x != 0:
                    acc_x -= step_x
                    step_y = random.choice((-1, 0, 0, 0, 0, 1))
                    direct.moveRel(step_x, step_y, relative=True)
                time.sleep(dt)

    elif cmd == "купить" and len(args) == 2:
        w1, w2 = args
        cat = NUMBERS.get(w1)
        slot = NUMBERS.get(w2)
        if cat and slot:
            buy(cat, slot)

    elif cmd == "столб" and len(args) == 3:
        w1, w2, w3 = args
        if w2 == "слот":
            cat = NUMBERS.get(w1)
            slot = NUMBERS.get(w3)
            if cat and slot:
                buy(cat, slot)

    elif cmd == "стреляй":
        shots = parse_number_words(args, 3)
        if shots >= 8:
            direct.mouseDown(button="left")
            human_sleep(shots * 0.09, shots * 0.11)
            direct.mouseUp(button="left")
        else:
            for _ in range(shots):
                human_click("left")
                human_sleep(0.075, 0.125)

    elif text == "очередь":
        direct.mouseDown(button="left")
        human_sleep(0.27, 0.36)
        direct.mouseUp(button="left")

    elif cmd == "ползи":
        if args:
            first_arg = next(iter(args))
            if first_arg in DURATIONS:
                is_crouching = False
                duration = min(DURATIONS.get(first_arg, 1.0), 10.0)
                direct.keyDown("ctrl")
                human_sleep(duration * 0.95, duration * 1.05)
                direct.keyUp("ctrl")
                return
        is_crouching = True
        direct.keyDown("ctrl")
        while is_crouching:
            human_sleep(0.04, 0.07)
        direct.keyUp("ctrl")

    elif text == "встань":
        is_crouching = False
        direct.keyUp("ctrl")

    elif text == "тихо":
        direct.keyDown("shift")

    elif text == "бегом":
        direct.keyUp("shift")

    elif cmd == "прямо":
        if args:
            first_arg = next(iter(args))
            if first_arg in DURATIONS:
                is_running_forward = False
                duration = DURATIONS.get(first_arg, 1.0)
                direct.keyDown("w")
                human_sleep(duration * 0.95, duration * 1.05)
                direct.keyUp("w")
                return
        is_running_forward = True
        direct.keyDown("w")
        while is_running_forward:
            human_sleep(0.04, 0.07)
        direct.keyUp("w")

    elif text == "прыжок":
        tap("space")

    elif text == "прыжок прямо":
        is_running_forward = False
        direct.keyDown("w")
        human_sleep(0.17, 0.24)
        direct.keyDown("space")
        human_sleep(0.02, 0.04)
        direct.keyDown("ctrl")
        human_sleep(0.04, 0.07)
        direct.keyUp("space")
        human_sleep(0.45, 0.55)
        direct.keyUp("w")
        direct.keyUp("ctrl")

    elif text == "назад":
        direct.keyDown("s")
        human_sleep(0.72, 0.88)
        direct.keyUp("s")

    elif text == "лево":
        direct.keyDown("a")
        human_sleep(0.24, 0.36)
        direct.keyUp("a")

    elif text == "право":
        direct.keyDown("d")
        human_sleep(0.24, 0.36)
        direct.keyUp("d")

    elif text == "огонь":
        human_click("left")

    elif text == "прицел":
        human_click("right")

    elif text == "перезарядка" or text == "обойма":
        tap("r")

    elif text == "сброс":
        tap("g")

    elif text == "закуп" or text == "закрыть":
        tap("b")

    elif text == "винтовка":
        tap("1")

    elif text == "пистолет":
        tap("2")

    elif text == "нож":
        tap("2")
        human_sleep(0.045, 0.085)
        tap("3")

    elif text == "зевс":
        tap("2")
        human_sleep(0.045, 0.085)
        tap("3")
        human_sleep(0.045, 0.085)
        tap("3")

    elif text == "бомба":
        tap("5")

    elif text == "граната":
        tap("6")

    elif text == "флешка":
        tap("7")

    elif text == "дым":
        tap("8")

    elif text == "молотов":
        tap("0")

def execute_async(text):
    executor.submit(run_command, text)

with sd.RawInputStream(samplerate=16000, blocksize=600, dtype="int16", channels=1, callback=callback):
    print("Говорите.....")
    while True:
        data = q.get()
        now = time.time()

        if now < ignore_until:
            recognizer.AcceptWaveform(data)
            recognizer.Reset()
            continue

        if recognizer.AcceptWaveform(data):
            result = json.loads(recognizer.Result())
            text = result.get("text", "")
            last_partial = ""
            partial_hits = 0
            if text:
                execute_async(text)
        else:
            partial = json.loads(recognizer.PartialResult()).get("partial", "")
            if not partial:
                last_partial = ""
                partial_hits = 0
                continue

            if partial == last_partial:
                partial_hits += 1
            else:
                last_partial = partial
                partial_hits = 1
                last_partial_change = now

            if partial_hits >= 2 and partial in INSTANT_COMMANDS:
                execute_async(partial)
                recognizer.Reset()
                last_partial = ""
                partial_hits = 0
                ignore_until = now + 0.28

            elif (now - last_partial_change) >= 0.45:
                final_res = json.loads(recognizer.FinalResult())
                final_text = final_res.get("text", "") or partial
                execute_async(final_text)
                recognizer.Reset()
                last_partial = ""
                partial_hits = 0
                ignore_until = now + 0.25
