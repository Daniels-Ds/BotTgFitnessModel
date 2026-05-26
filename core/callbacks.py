"""Short stable callback_data for inline keyboards (Telegram limit 64 bytes)."""


class CB:
    START_FLOW = "start_flow"

    GENDER_MALE = "g_male"
    GENDER_FEMALE = "g_female"

    ACT_LOW = "act_low"
    ACT_MID = "act_mid"
    ACT_HIGH = "act_high"

    CYCLE_MENSTRUATION = "cyc_men"
    CYCLE_FOLLICULAR = "cyc_foll"
    CYCLE_OVULATION = "cyc_ovu"
    CYCLE_LUTEAL = "cyc_lut"
    CYCLE_UNKNOWN = "cyc_skip"

    CONFIRM = "confirm_generate"
    EDIT = "edit_params"
    EDIT_PROFILE = "edit_profile"
    EDIT_MUSCLES = "edit_muscles"
    EDIT_BACK = "edit_back"

    WORKOUT = "get_workout"
    WORKOUT_REFRESH = "wo_refresh"

    NUTRITION = "get_nutrition"
    MEASUREMENTS = "body_measurements"
    MEASUREMENTS_VIEW = "body_measurements_view"
    RESTART = "restart"

    WATER_ADD = "water_add"
    WATER_RESET = "water_reset"

    PHOTO_REPLACE = "ph_replace"
    PHOTO_RESTART_ALL = "ph_restart"
    PHOTO_KEEP = "ph_keep"
