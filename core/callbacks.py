"""Short stable callback_data for inline keyboards (Telegram limit 64 bytes)."""


class CB:
    START_FLOW = "start_flow"

    GENDER_MALE = "g_male"
    GENDER_FEMALE = "g_female"

    ACT_LOW = "act_low"
    ACT_MID = "act_mid"
    ACT_HIGH = "act_high"

    CONFIRM = "confirm_generate"
    EDIT = "edit_params"
    EDIT_PROFILE = "edit_profile"
    EDIT_MUSCLES = "edit_muscles"
    EDIT_BACK = "edit_back"

    WORKOUT = "get_workout"
    # Календарь тренировок по неделям (см. workout_plan_kb)
    PLAN_W1 = "pl_w1"
    PLAN_W2 = "pl_w2"
    PLAN_W3 = "pl_w3"
    PLAN_W4 = "pl_w4"
    PLAN_TODAY = "pl_td"
    PLAN_HUB_BACK = "pl_bk"
    PLAN_RESET = "pl_rs"

    NUTRITION = "get_nutrition"
    MEASUREMENTS = "body_measurements"
    MEASUREMENTS_VIEW = "body_measurements_view"
    RESTART = "restart"

    WATER_ADD = "water_add"
    WATER_RESET = "water_reset"
