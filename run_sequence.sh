#!/bin/zsh

PICO="http://youpicosipaddress:8080"

# -----------------------
# Timing variables
# -----------------------

RESET_TIME=2
LOAD_TIME=0.5
TEXT_TIME=0.5
LONG_TEXT_TIME=1
DEFAULT_TIME=0.5

# -----------------------
# Start timer
# -----------------------

zmodload zsh/datetime
START_TIME=$EPOCHREALTIME

# -----------------------
# Helper functions
# -----------------------

press() {
  local BUTTON=$1
  local DELAY=$2

  if [[ -z "$DELAY" ]]; then
    DELAY=$DEFAULT_TIME
  fi

  echo "Pressing $BUTTON (delay $DELAY)"
  curl -s -X POST "$PICO/cmd" -d "press $BUTTON 120"
    sleep "$DELAY"

}

reset_game() {
  echo "Resetting game"
  curl -s -X POST "$PICO/reset"
}

wait_time() {
  local TIME=$1
  echo "Waiting $TIME seconds"
  sleep "$TIME"
}

# -----------------------
# Sequence
# -----------------------

echo "Starting sequence..."

reset_game
wait_time "$RESET_TIME"

press + "$LOAD_TIME"
press + "$LOAD_TIME"
press + "$LOAD_TIME"
press + "$LOAD_TIME"
press + "$LOAD_TIME"
press + 1

wait_time 1

echo "should be loading saved file"

for i in {1..7}
do
  press A "$TEXT_TIME"
done

echo "should be picking pokemon"
for i in {1..6}
do
  press A "$TEXT_TIME"
done

press A 1

echo "no to rename"
press B 0.5
press B 0.5

echo "rival should be picking pokemon"
press B 0.5
press B 0.5
press B 0.5
press B 0.5
press B 1.0
press B 1.0
press B 1.0
press B 1.0
press B 1.0
press B 1.0
press B 1.5

press + 1.5

press A 1.0
press A 0.5
press A 1.0
press A 0.0

echo "Sequence complete"

# -----------------------
# End timer
# -----------------------

END_TIME=$EPOCHREALTIME
ELAPSED=$(printf "%.3f" "$(( END_TIME - START_TIME ))")

echo "--------------------------------"
echo "Total runtime: $ELAPSED seconds"
echo "--------------------------------"