# Global mutable app state — import this module to read/write shared flags.
offline_mode     = False
offline_notified = False  # True once the "now offline" warning has been shown this session
checking_online  = False  # Set before reloading when user manually toggles offline → online
