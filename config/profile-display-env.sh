# Sourced by non-interactive Bash shells through BASH_ENV. This mirrors the
# cua-driver wrapper so an agent asking its terminal for DISPLAY sees the exact
# profile-scoped display that computer_use receives.
if hermes_profile_display=$(
  /usr/local/libexec/profile-displays.py current /opt/data/.displays.json 2>/dev/null
); then
  export DISPLAY="$hermes_profile_display"
fi
unset hermes_profile_display
