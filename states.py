from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    photos       = State()   # загрузка 3 фото
    gender       = State()   # пол
    age          = State()   # возраст (текстовый ввод)
    height       = State()   # рост
    weight       = State()   # вес
    activity     = State()   # уровень активности
    cycle        = State()   # фаза цикла (только женщины)
    muscles      = State()   # выбор групп мышц + %
    generating   = State()   # идёт генерация


class PostGen(StatesGroup):
    menu         = State()   # меню после получения видео
    edit_params  = State()   # редактирование параметров


class Measurements(StatesGroup):
    waist = State()
    hips = State()
    chest = State()
    shoulders = State()
    thigh = State()
    calf = State()
    biceps = State()
    photo = State()
